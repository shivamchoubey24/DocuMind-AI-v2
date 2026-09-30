"""
Retrieval-augmented generation with token-by-token streaming.

Design notes for reviewers:
- Retrieval is synchronous (fast: local FAISS similarity search).
- Generation is streamed from Groq using LangChain's async streaming
  interface and yielded to the client as Server-Sent Events, so the UI can
  render tokens as they arrive instead of waiting for the full answer.
- Conversation history is loaded from Postgres/SQLite per chat session
  (not kept in server memory), so it survives restarts and scales across
  multiple backend replicas.
"""
import asyncio
import json
import time
from collections.abc import AsyncGenerator

from langchain.docstore.document import Document as LCDocument
from langchain.prompts import PromptTemplate
from langchain_groq import ChatGroq

from app.config import get_settings
from app.core.exceptions import DocuMindError
from app.core.logging_config import logger
from app.documents.processing import load_user_index

settings = get_settings()

CONDENSE_QUESTION_PROMPT = PromptTemplate.from_template(
    """Given the following conversation and a follow-up question, rephrase the
follow-up question to be a standalone question, in its original language.
If the follow-up question is already standalone, return it unchanged.

Chat History:
{chat_history}
Follow-up question: {question}
Standalone question:"""
)

ANSWER_PROMPT = PromptTemplate.from_template(
    """You are DocuMind AI, a knowledgeable assistant answering questions using
the provided document excerpts as your source of truth.

How to answer:
- Read the excerpts, understand the underlying concept, then explain it in
  your OWN words as if teaching someone — do not copy sentences or phrases
  verbatim from the excerpts, and do not just rephrase them line-by-line in
  the same order. Synthesize a coherent explanation.
- It's fine, and encouraged, to add a brief clarifying example or analogy if
  it helps understanding, as long as it stays consistent with the excerpts.
- Write naturally and conversationally, not like a dry textbook restatement.
- If the answer isn't contained in the excerpts, say so honestly rather than
  guessing or fabricating information.
- Do not mention "the excerpts" or "the document" explicitly in your answer
  (e.g. don't say "According to excerpt 2..."); just answer the question
  directly. Sources are shown to the user separately.

Document excerpts:
{context}

Chat History:
{chat_history}

Question: {question}

Answer (in your own words):"""
)


def _format_history(history: list[tuple[str, str]]) -> str:
    lines = []
    for role, content in history:
        speaker = "Human" if role == "user" else "Assistant"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def _condense_question(question: str, history: list[tuple[str, str]], llm: ChatGroq) -> str:
    if not history:
        return question
    prompt = CONDENSE_QUESTION_PROMPT.format(chat_history=_format_history(history), question=question)
    resp = llm.invoke(prompt)
    return resp.content.strip() or question


def retrieve(user_id: str, question: str, document_ids: list[str] | None = None) -> list[LCDocument]:
    store = load_user_index(user_id)
    # MMR (max-marginal-relevance) trades a bit of pure similarity for
    # diversity between the returned chunks, so we don't pull back several
    # near-duplicate slices of the same paragraph (which is what was causing
    # the same source card to show up 2-3 times in a row).
    search_kwargs = {"k": settings.RETRIEVER_K, "fetch_k": settings.RETRIEVER_K * 4, "lambda_mult": 0.5}
    if document_ids:
        # Scope retrieval to a subset of the user's documents (a per-session
        # setting). FAISS's `filter` accepts either a dict of exact-match
        # metadata fields or a callable — we need "is one of several ids",
        # so a callable is the only option here.
        allowed = set(document_ids)
        search_kwargs["filter"] = lambda meta: meta.get("document_id") in allowed
    retriever = store.as_retriever(search_type="mmr", search_kwargs=search_kwargs)
    docs = retriever.invoke(question)
    return _dedupe_documents(docs)


def _dedupe_documents(docs: list[LCDocument]) -> list[LCDocument]:
    """Belt-and-suspenders dedupe: MMR reduces near-duplicates, but if two
    chunks still have effectively the same content (e.g. small chunk overlap
    straddling the same sentence), only keep the first occurrence."""
    seen = set()
    unique = []
    for d in docs:
        key = (d.metadata.get("source"), d.metadata.get("page"), d.page_content[:200].strip())
        if key in seen:
            continue
        seen.add(key)
        unique.append(d)
    return unique


async def stream_answer(
    user_id: str,
    question: str,
    history: list[tuple[str, str]],
    document_ids: list[str] | None = None,
) -> AsyncGenerator[str, None]:
    """Yields Server-Sent-Event formatted strings.

    Event types sent to the client:
      - {"type": "sources", "sources": [...]}   (once, before tokens)
      - {"type": "token", "text": "..."}         (repeated, streamed answer)
      - {"type": "done", "latency_ms": 1234}     (once, at the end)
      - {"type": "error", "message": "..."}
    """
    if not settings.GROQ_API_KEY:
        yield _sse({"type": "error", "message": "Server is missing GROQ_API_KEY. Set it in the backend .env file."})
        return

    start = time.time()
    llm = ChatGroq(temperature=0.55, model_name=settings.GROQ_MODEL, groq_api_key=settings.GROQ_API_KEY)

    try:
        # _condense_question and retrieve() are both blocking (sync FAISS /
        # HuggingFace / Groq-SDK calls) — run them in a worker thread so
        # they don't stall the event loop for other concurrent requests
        # while this one is thinking.
        standalone_question = await asyncio.to_thread(_condense_question, question, history, llm)
        docs = await asyncio.to_thread(retrieve, user_id, standalone_question, document_ids)
    except DocuMindError as e:
        yield _sse({"type": "error", "message": e.message})
        return
    except Exception as e:  # noqa: BLE001
        yield _sse({"type": "error", "message": f"Retrieval failed: {e}"})
        return

    retrieval_ms = int((time.time() - start) * 1000)
    logger.info("chat retrieval took %dms (user=%s, %d docs)", retrieval_ms, user_id, len(docs))

    sources = [
        {
            "source": d.metadata.get("source", "unknown"),
            "page": d.metadata.get("page", 1),
            "snippet": d.page_content[:280].replace("\n", " ").strip(),
            "document_id": d.metadata.get("document_id"),
        }
        for d in docs
    ]
    yield _sse({"type": "sources", "sources": sources})

    context = "\n\n---\n\n".join(d.page_content for d in docs) if docs else "(no relevant excerpts found)"
    prompt = ANSWER_PROMPT.format(context=context, chat_history=_format_history(history), question=question)

    full_answer = []
    try:
        async for chunk in llm.astream(prompt):
            text = chunk.content or ""
            if text:
                full_answer.append(text)
                yield _sse({"type": "token", "text": text})
    except Exception as e:  # noqa: BLE001
        yield _sse({"type": "error", "message": f"Generation failed: {e}"})
        return

    latency_ms = int((time.time() - start) * 1000)
    logger.info(
        "chat generation took %dms (total %dms, user=%s)",
        latency_ms - retrieval_ms,
        latency_ms,
        user_id,
    )
    yield _sse({"type": "done", "latency_ms": latency_ms, "answer": "".join(full_answer), "sources": sources})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
