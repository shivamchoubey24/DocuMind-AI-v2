"""
Text extraction, chunking, and per-user FAISS vector store management.

Each user gets an isolated FAISS index on disk at
    storage/vectorstores/<user_id>/
so one user's documents are never retrievable by another user — a hard
requirement once you go from a single-user prototype to a real multi-tenant
product.
"""
import os
import shutil
from functools import lru_cache

from docx import Document as DocxDocument
from langchain.docstore.document import Document as LCDocument
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from app.config import get_settings
from app.core.exceptions import DocuMindError
from app.core.logging_config import logger

settings = get_settings()


@lru_cache
def get_embeddings() -> HuggingFaceEmbeddings:
    # Cached process-wide: loading the embedding model is the slowest part
    # of a cold start, so we only ever pay that cost once per process.
    return HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL, model_kwargs={"device": "cpu"})


def user_vectorstore_path(user_id: str) -> str:
    return os.path.join(settings.VECTORSTORE_DIR, user_id)


def extract_documents(file_path: str, filename: str, ext: str) -> list[LCDocument]:
    docs: list[LCDocument] = []
    try:
        if ext == "pdf":
            reader = PdfReader(file_path)
            for page_num, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    docs.append(LCDocument(page_content=text, metadata={"source": filename, "page": page_num, "ext": ext}))
        elif ext == "txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            if text.strip():
                docs.append(LCDocument(page_content=text, metadata={"source": filename, "page": 1, "ext": ext}))
        elif ext == "docx":
            d = DocxDocument(file_path)
            text = "\n".join(p.text for p in d.paragraphs)
            if text.strip():
                docs.append(LCDocument(page_content=text, metadata={"source": filename, "page": 1, "ext": ext}))
        else:
            raise DocuMindError(f"Unsupported file type: {ext}")
    except DocuMindError:
        raise
    except Exception as e:
        logger.exception("Failed to extract text from %s", filename)
        raise DocuMindError(f"Could not read {filename}: {e}") from e

    if not docs:
        raise DocuMindError(f"No extractable text found in {filename} (it may be a scanned/image-only file)")
    return docs


def chunk_documents(docs: list[LCDocument]) -> list[LCDocument]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        length_function=len,
    )
    # Tag every chunk with a document_id so we can later delete just this
    # document's vectors without rebuilding the whole index.
    return splitter.split_documents(docs)


def add_document_to_index(user_id: str, document_id: str, chunks: list[LCDocument]) -> None:
    for c in chunks:
        c.metadata["document_id"] = document_id

    path = user_vectorstore_path(user_id)
    embeddings = get_embeddings()

    if os.path.isdir(path) and os.listdir(path):
        store = FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)
        store.add_documents(chunks)
    else:
        store = FAISS.from_documents(chunks, embeddings)

    os.makedirs(path, exist_ok=True)
    store.save_local(path)


def load_user_index(user_id: str) -> FAISS:
    path = user_vectorstore_path(user_id)
    if not (os.path.isdir(path) and os.listdir(path)):
        raise DocuMindError("You haven't uploaded any processed documents yet.", status_code=404)
    return FAISS.load_local(path, get_embeddings(), allow_dangerous_deserialization=True)


def remove_document_from_index(user_id: str, document_id: str) -> None:
    """Rebuild the user's index excluding the given document's vectors.

    FAISS doesn't support cheap per-document deletion, so for a portfolio
    project we accept the O(n) rebuild cost; a production system with heavy
    delete traffic would swap FAISS for a store with native deletes
    (pgvector, Qdrant, Chroma) — noted in the README's "next steps" section.
    """
    path = user_vectorstore_path(user_id)
    if not (os.path.isdir(path) and os.listdir(path)):
        return
    embeddings = get_embeddings()
    store = FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)

    ids_to_remove = [
        doc_id
        for doc_id, doc in store.docstore._dict.items()
        if doc.metadata.get("document_id") == document_id
    ]
    if ids_to_remove:
        store.delete(ids_to_remove)
        store.save_local(path)


def delete_user_index(user_id: str) -> None:
    path = user_vectorstore_path(user_id)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
