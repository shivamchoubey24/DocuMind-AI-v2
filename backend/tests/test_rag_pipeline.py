"""
Unit tests for the RAG pipeline itself (extraction -> chunking -> indexing
-> retrieval), independent of the HTTP layer. These were previously
untested — chat/router.py and the auth/document HTTP tests only covered the
API surface, not whether retrieval actually returns the right chunks, dedupes
correctly, or respects per-session document scoping.

Uses the same deterministic `_FakeEmbeddings` stand-in as conftest.py (no
network calls, no real transformer model) so this stays fast.
"""
import os

import pytest
from langchain.docstore.document import Document as LCDocument

from app.chat.rag import _dedupe_documents, retrieve
from app.core.exceptions import DocuMindError
from app.documents.processing import (
    add_document_to_index,
    chunk_documents,
    extract_documents,
    remove_document_from_index,
)


# --- extraction ---

def test_extract_txt_reads_content(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("Hello world, this is a test document about RAG pipelines.")
    docs = extract_documents(str(p), "notes.txt", "txt")
    assert len(docs) == 1
    assert "RAG pipelines" in docs[0].page_content
    assert docs[0].metadata["source"] == "notes.txt"
    assert docs[0].metadata["page"] == 1


def test_extract_empty_file_raises(tmp_path):
    p = tmp_path / "empty.txt"
    p.write_text("   \n  ")
    with pytest.raises(DocuMindError):
        extract_documents(str(p), "empty.txt", "txt")


def test_extract_unsupported_extension_raises(tmp_path):
    p = tmp_path / "file.xyz"
    p.write_text("content")
    with pytest.raises(DocuMindError):
        extract_documents(str(p), "file.xyz", "xyz")


def test_extract_missing_file_raises_documind_error(tmp_path):
    with pytest.raises(DocuMindError):
        extract_documents(str(tmp_path / "does_not_exist.txt"), "does_not_exist.txt", "txt")


# --- chunking ---

def test_chunk_documents_splits_long_text():
    long_text = "Sentence about DocuMind AI and retrieval augmented generation. " * 100
    docs = [LCDocument(page_content=long_text, metadata={"source": "big.txt", "page": 1})]
    chunks = chunk_documents(docs)
    assert len(chunks) > 1
    # metadata (source/page) must survive the split so citations stay correct
    assert all(c.metadata["source"] == "big.txt" for c in chunks)


def test_chunk_documents_keeps_short_text_as_one_chunk():
    docs = [LCDocument(page_content="Short document.", metadata={"source": "s.txt", "page": 1})]
    chunks = chunk_documents(docs)
    assert len(chunks) == 1
    assert chunks[0].page_content == "Short document."


# --- dedupe ---

def test_dedupe_documents_removes_near_duplicate_chunks():
    docs = [
        LCDocument(page_content="A" * 250, metadata={"source": "x.pdf", "page": 1}),
        LCDocument(page_content="A" * 250 + "extra tail text", metadata={"source": "x.pdf", "page": 1}),
        LCDocument(page_content="totally different content", metadata={"source": "x.pdf", "page": 2}),
    ]
    deduped = _dedupe_documents(docs)
    # first two share the same first-200-chars key + source + page -> collapse to one
    assert len(deduped) == 2


def test_dedupe_documents_keeps_same_text_on_different_pages():
    docs = [
        LCDocument(page_content="Repeated boilerplate footer text", metadata={"source": "x.pdf", "page": 1}),
        LCDocument(page_content="Repeated boilerplate footer text", metadata={"source": "x.pdf", "page": 2}),
    ]
    assert len(_dedupe_documents(docs)) == 2


# --- indexing + retrieval ---

def test_add_and_retrieve_document(monkeypatch):
    user_id = "rag-test-user-1"
    docs = [LCDocument(page_content="The mitochondria is the powerhouse of the cell.", metadata={"source": "bio.txt", "page": 1})]
    chunks = chunk_documents(docs)
    add_document_to_index(user_id, "doc-1", chunks)

    results = retrieve(user_id, "What is the powerhouse of the cell?")
    assert len(results) >= 1
    assert any("mitochondria" in d.page_content.lower() for d in results)
    assert results[0].metadata["document_id"] == "doc-1"


def test_retrieve_with_no_index_raises_documind_error():
    with pytest.raises(DocuMindError):
        retrieve("user-with-no-documents-ever", "anything")


def test_retrieve_scoped_to_document_ids_excludes_other_documents():
    user_id = "rag-test-user-2"
    doc_a = chunk_documents(
        [LCDocument(page_content="Apples are a type of fruit that grow on trees.", metadata={"source": "a.txt", "page": 1})]
    )
    doc_b = chunk_documents(
        [LCDocument(page_content="Apples are also a well known technology company.", metadata={"source": "b.txt", "page": 1})]
    )
    add_document_to_index(user_id, "doc-a", doc_a)
    add_document_to_index(user_id, "doc-b", doc_b)

    # Unscoped: both documents are eligible.
    unscoped = retrieve(user_id, "Tell me about apples")
    found_doc_ids = {d.metadata["document_id"] for d in unscoped}
    assert "doc-a" in found_doc_ids or "doc-b" in found_doc_ids

    # Scoped to doc-a only: doc-b must never appear, regardless of relevance.
    scoped = retrieve(user_id, "Tell me about apples", document_ids=["doc-a"])
    assert all(d.metadata["document_id"] == "doc-a" for d in scoped)
    assert len(scoped) >= 1


def test_retrieve_scoped_to_unknown_document_id_returns_nothing():
    user_id = "rag-test-user-3"
    chunks = chunk_documents(
        [LCDocument(page_content="Some content about oceans and marine biology.", metadata={"source": "c.txt", "page": 1})]
    )
    add_document_to_index(user_id, "doc-c", chunks)

    scoped = retrieve(user_id, "oceans", document_ids=["some-other-document-id"])
    assert scoped == []


def test_remove_document_from_index_drops_its_chunks():
    user_id = "rag-test-user-4"
    doc_a = chunk_documents(
        [LCDocument(page_content="Volcanoes erupt molten rock called lava.", metadata={"source": "a.txt", "page": 1})]
    )
    doc_b = chunk_documents(
        [LCDocument(page_content="Glaciers are large moving masses of ice.", metadata={"source": "b.txt", "page": 1})]
    )
    add_document_to_index(user_id, "doc-a", doc_a)
    add_document_to_index(user_id, "doc-b", doc_b)

    remove_document_from_index(user_id, "doc-a")

    remaining = retrieve(user_id, "volcanoes lava glaciers ice")
    assert all(d.metadata["document_id"] != "doc-a" for d in remaining)
    assert any(d.metadata["document_id"] == "doc-b" for d in remaining)
