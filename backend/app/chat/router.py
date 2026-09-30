import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.chat.rag import stream_answer
from app.config import get_settings
from app.core.rate_limit import limiter
from app.deps import get_current_user, get_db

router = APIRouter(prefix="/chat", tags=["chat"])
settings = get_settings()


def _session_out(session: models.ChatSession) -> schemas.ChatSessionOut:
    doc_ids = json.loads(session.document_ids_json) if session.document_ids_json else []
    return schemas.ChatSessionOut(
        id=session.id, title=session.title, document_ids=doc_ids, created_at=session.created_at
    )


def _validate_document_ids(db: Session, user_id: str, document_ids: list[str]) -> None:
    """Scoping to a document you don't own (or that doesn't exist) would let
    retrieval silently return nothing with no clear reason why, so reject it
    up front with a clear error instead."""
    if not document_ids:
        return
    owned = (
        db.query(models.Document.id)
        .filter(models.Document.owner_id == user_id, models.Document.id.in_(document_ids))
        .all()
    )
    owned_ids = {row[0] for row in owned}
    missing = set(document_ids) - owned_ids
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown document id(s): {', '.join(sorted(missing))}")


@router.post("/sessions", response_model=schemas.ChatSessionOut, status_code=201)
def create_session(
    payload: schemas.ChatSessionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _validate_document_ids(db, current_user.id, payload.document_ids or [])
    session = models.ChatSession(
        owner_id=current_user.id,
        title=payload.title or "New chat",
        document_ids_json=json.dumps(payload.document_ids) if payload.document_ids else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(session)


@router.get("/sessions", response_model=list[schemas.ChatSessionOut])
def list_sessions(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    sessions = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.owner_id == current_user.id)
        .order_by(models.ChatSession.created_at.desc())
        .all()
    )
    return [_session_out(s) for s in sessions]


@router.patch("/sessions/{session_id}", response_model=schemas.ChatSessionOut)
def rename_session(
    session_id: str,
    payload: schemas.ChatSessionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    session = _get_owned_session(db, session_id, current_user.id)
    session.title = payload.title.strip() or session.title
    db.commit()
    db.refresh(session)
    return _session_out(session)


@router.patch("/sessions/{session_id}/scope", response_model=schemas.ChatSessionOut)
def update_session_scope(
    session_id: str,
    payload: schemas.ChatSessionScopeUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Restrict (or clear) which documents a chat session's retrieval is
    scoped to. Useful once a user has several documents uploaded but only
    wants this conversation to consider one or two of them."""
    session = _get_owned_session(db, session_id, current_user.id)
    _validate_document_ids(db, current_user.id, payload.document_ids or [])
    session.document_ids_json = json.dumps(payload.document_ids) if payload.document_ids else None
    db.commit()
    db.refresh(session)
    return _session_out(session)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    session = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.id == session_id, models.ChatSession.owner_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    db.delete(session)
    db.commit()


@router.get("/sessions/{session_id}/messages", response_model=list[schemas.ChatMessageOut])
def get_messages(
    session_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    session = _get_owned_session(db, session_id, current_user.id)
    out = []
    for m in session.messages:
        sources = json.loads(m.sources_json) if m.sources_json else []
        out.append(
            schemas.ChatMessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                sources=sources,
                latency_ms=m.latency_ms,
                created_at=m.created_at,
            )
        )
    return out


def _get_owned_session(db: Session, session_id: str, user_id: str) -> models.ChatSession:
    session = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.id == session_id, models.ChatSession.owner_id == user_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.post("/stream")
@limiter.limit(settings.RATE_LIMIT_CHAT)
async def chat_stream(
    request: Request,
    payload: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Server-Sent Events endpoint: streams the answer token by token.

    We persist the user message immediately, then persist the assistant
    message once streaming completes (with full text + sources + latency),
    so history is durable even if the client disconnects mid-stream.
    """
    session = _get_owned_session(db, payload.session_id, current_user.id)

    history = [(m.role, m.content) for m in session.messages[-12:]]  # cap context window
    scoped_document_ids = json.loads(session.document_ids_json) if session.document_ids_json else None

    user_msg = models.ChatMessage(session_id=session.id, role="user", content=payload.question)
    db.add(user_msg)
    if session.title == "New chat":
        session.title = payload.question[:60]
    db.commit()

    # Capture plain values now, while `db` (and therefore `current_user` /
    # `session`) is still open. The request's DB session is closed by
    # FastAPI's dependency teardown as soon as this function returns, but
    # event_generator() below keeps running after that (that's the whole
    # point of StreamingResponse) — so it must never touch the ORM objects
    # themselves, only these captured values, or it hits
    # sqlalchemy.orm.exc.DetachedInstanceError mid-stream.
    user_id = current_user.id
    session_id = session.id

    async def event_generator():
        collected_answer = []
        collected_sources = []
        latency_ms = None
        async for event in stream_answer(user_id, payload.question, history, document_ids=scoped_document_ids):
            yield event
            try:
                data = json.loads(event[len("data: "):].strip())
            except (ValueError, IndexError):
                continue
            if data.get("type") == "done":
                collected_answer = [data.get("answer", "")]
                collected_sources = data.get("sources", [])
                latency_ms = data.get("latency_ms")

        # Persist the assistant turn after the stream finishes.
        from app.database import SessionLocal

        persist_db = SessionLocal()
        try:
            assistant_msg = models.ChatMessage(
                session_id=session_id,
                role="assistant",
                content="".join(collected_answer) or "(no response generated)",
                sources_json=json.dumps(collected_sources),
                latency_ms=latency_ms,
            )
            persist_db.add(assistant_msg)
            persist_db.commit()
        finally:
            persist_db.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
