import asyncio
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import get_settings
from app.core.exceptions import DocuMindError
from app.core.logging_config import logger
from app.core.rate_limit import limiter
from app.deps import get_current_user, get_current_user_for_file, get_db
from app.documents.processing import (
    add_document_to_index,
    chunk_documents,
    extract_documents,
    remove_document_from_index,
)

router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()

SUPPORTED_EXTENSIONS = {"pdf", "txt", "docx"}
MIME_TYPES = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def _process_document(document_id: str, user_id: str, file_path: str, filename: str, ext: str) -> None:
    """Runs in a background task so the upload request returns immediately."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        doc_row = db.query(models.Document).filter(models.Document.id == document_id).first()
        if doc_row is None:
            return
        try:
            raw_docs = extract_documents(file_path, filename, ext)
            chunks = chunk_documents(raw_docs)
            add_document_to_index(user_id, document_id, chunks)

            doc_row.status = "ready"
            doc_row.num_chunks = len(chunks)
            doc_row.num_pages = len({d.metadata.get("page", 1) for d in raw_docs})
        except DocuMindError as e:
            doc_row.status = "failed"
            doc_row.error_message = e.message
            logger.warning("Document processing failed for %s: %s", filename, e.message)
        except Exception:  # noqa: BLE001
            doc_row.status = "failed"
            doc_row.error_message = "Unexpected error while processing this file."
            logger.exception("Unexpected error processing %s", filename)
        db.commit()
    finally:
        db.close()


@router.post("/upload", response_model=list[schemas.DocumentOut], status_code=status.HTTP_202_ACCEPTED)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_documents(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    if len(files) > settings.MAX_FILES_PER_UPLOAD:
        raise HTTPException(status_code=400, detail=f"Max {settings.MAX_FILES_PER_UPLOAD} files per upload")

    existing_count = db.query(models.Document).filter(models.Document.owner_id == current_user.id).count()
    if existing_count + len(files) > settings.MAX_DOCUMENTS_PER_USER:
        raise HTTPException(status_code=400, detail="Document limit reached for this account")

    user_dir = os.path.join(settings.UPLOAD_DIR, current_user.id)
    os.makedirs(user_dir, exist_ok=True)

    created: list[models.Document] = []
    for file in files:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.filename}")

        contents = await file.read()
        size_mb = len(contents) / (1024 * 1024)
        if size_mb > settings.MAX_UPLOAD_MB:
            raise HTTPException(status_code=400, detail=f"{file.filename} exceeds {settings.MAX_UPLOAD_MB}MB limit")

        document_id = str(uuid.uuid4())
        stored_name = f"{document_id}.{ext}"
        stored_path = os.path.join(user_dir, stored_name)

        await asyncio.to_thread(Path(stored_path).write_bytes, contents)

        doc_row = models.Document(
            id=document_id,
            owner_id=current_user.id,
            filename=file.filename,
            extension=ext,
            size_bytes=len(contents),
            status="processing",
        )
        db.add(doc_row)
        created.append(doc_row)

        background_tasks.add_task(_process_document, document_id, current_user.id, stored_path, file.filename, ext)

    db.commit()
    for d in created:
        db.refresh(d)
    return created


@router.get("", response_model=list[schemas.DocumentOut])
def list_documents(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return (
        db.query(models.Document)
        .filter(models.Document.owner_id == current_user.id)
        .order_by(models.Document.created_at.desc())
        .all()
    )


@router.get("/{document_id}/file/exists")
def check_document_file_exists(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Cheap existence check used by the frontend's source-citation preview
    before it points an <iframe> at the file — avoids showing the browser's
    own opaque "not found" page inside our modal for a deleted/stale doc."""
    doc_row = (
        db.query(models.Document)
        .filter(models.Document.id == document_id, models.Document.owner_id == current_user.id)
        .first()
    )
    if not doc_row:
        return {"exists": False}
    file_path = os.path.join(settings.UPLOAD_DIR, current_user.id, f"{document_id}.{doc_row.extension}")
    return {"exists": os.path.exists(file_path)}


@router.get("/{document_id}/file")
def get_document_file(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_for_file),
):
    """Serves the original uploaded file for inline preview (e.g. an <iframe>
    pointed at this URL with a #page=N fragment for PDFs). Ownership is
    enforced the same as every other document endpoint."""
    doc_row = (
        db.query(models.Document)
        .filter(models.Document.id == document_id, models.Document.owner_id == current_user.id)
        .first()
    )
    if not doc_row:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = os.path.join(settings.UPLOAD_DIR, current_user.id, f"{document_id}.{doc_row.extension}")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File is no longer available on disk")

    return FileResponse(
        file_path,
        media_type=MIME_TYPES.get(doc_row.extension, "application/octet-stream"),
        filename=doc_row.filename,
        headers={"Content-Disposition": f'inline; filename="{doc_row.filename}"'},
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    doc_row = (
        db.query(models.Document)
        .filter(models.Document.id == document_id, models.Document.owner_id == current_user.id)
        .first()
    )
    if not doc_row:
        raise HTTPException(status_code=404, detail="Document not found")

    remove_document_from_index(current_user.id, document_id)

    file_path = os.path.join(settings.UPLOAD_DIR, current_user.id, f"{document_id}.{doc_row.extension}")
    if os.path.exists(file_path):
        os.remove(file_path)

    db.delete(doc_row)
    db.commit()
