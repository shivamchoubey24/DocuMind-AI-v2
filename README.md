# 📚 DocuMind AI — Production-Grade Multi-User RAG Chatbot

Chat with your PDF, DOCX, and TXT files. Every answer is grounded in your
documents and cited back to the exact source page.

This started as a single-file Streamlit prototype. It has been rebuilt as a
real client–server application: a **FastAPI backend** with authentication,
persistence, and a streaming RAG pipeline, and a **React frontend** — the
kind of architecture you'd actually deploy, not just demo locally.

---

## ✨ Features

| Area | What it does |
|---|---|
| **Multi-user accounts** | Email/password signup + JWT auth. Every user's documents, chat sessions, and vector index are fully isolated from every other user. |
| **Multi-format ingestion** | PDF (page-aware), DOCX, TXT. Background processing so uploads don't block the UI. |
| **RAG pipeline** | Chunking → local embeddings (`all-MiniLM-L6-v2`, no API cost) → per-user FAISS index → Groq (Llama 3.1) generation. |
| **Token-by-token streaming** | Answers stream to the browser via Server-Sent Events as they're generated, not all-at-once. |
| **Cited answers** | Every answer shows the exact source file + page + snippet it was grounded in. |
| **Persistent chat history** | Multiple named chat sessions per user, stored in a real database — survives restarts, works across browser sessions. |
| **Document management** | Upload, view processing status, delete documents (with automatic vector cleanup). |
| **Hardening** | Per-route rate limiting, file-size/type/count limits, structured error handling, centralized logging. |
| **Tests + CI** | Pytest suite (auth, multi-tenant isolation, document lifecycle) run automatically via GitHub Actions on every push. |
| **Containerized** | One `docker compose up` runs the whole stack with health checks. |

---

## 🏗️ Architecture

```
┌─────────────────┐        HTTPS/JSON + SSE        ┌──────────────────────┐
│   React SPA      │ ──────────────────────────────▶│   FastAPI backend     │
│  (Vite + Tailwind)│◀────────────────────────────── │                       │
└─────────────────┘        JWT bearer auth          │  ┌─────────────────┐  │
                                                      │  │ Auth (JWT)       │  │
                                                      │  ├─────────────────┤  │
                                                      │  │ Documents API    │  │
                                                      │  │  → extract/chunk │  │
                                                      │  │  → embed (local) │  │
                                                      │  ├─────────────────┤  │
                                                      │  │ Chat API (SSE)   │  │
                                                      │  │  → retrieve      │  │
                                                      │  │  → Groq stream   │  │
                                                      │  └─────────────────┘  │
                                                      └──────────┬────────────┘
                                                                 │
                                        ┌────────────────────────┼───────────────────────┐
                                        ▼                        ▼                        ▼
                                 SQLite/Postgres           Per-user FAISS            Groq API
                              (users, docs, chats)          index on disk         (Llama 3.1, streamed)
```

**Why these choices, for anyone asking in an interview:**
- **FastAPI** — async-native, so a streaming SSE endpoint and background
  document processing are first-class, plus free OpenAPI docs at `/api/docs`.
- **Per-user FAISS index on disk** instead of one shared index — the
  simplest correct way to guarantee tenant isolation without standing up
  Postgres/pgvector for a portfolio-scale project. The README below shows
  exactly what changes to move to a shared vector DB (Qdrant/pgvector) if
  you need horizontal scaling.
- **SQLite by default, Postgres via one env var** — zero-config to run
  locally, production-ready by changing `DATABASE_URL`.
- **Local embeddings, hosted generation** — embeddings run free/offline
  (`sentence-transformers`), so only generation needs an API key. Keeps the
  project runnable on Groq's free tier.
- **SSE over WebSockets for chat** — one-directional streaming is all this
  needs; SSE is simpler to reason about, auto-reconnects, and works through
  plain HTTP proxies.

---

## 🚀 Quick start (Docker — recommended)

```bash
git clone <your-repo-url>
cd documind

cp backend/.env.example backend/.env
# edit backend/.env and set GROQ_API_KEY (free key: https://console.groq.com)
# GROQ_MODEL defaults to openai/gpt-oss-20b — Groq's current fast/cheap
# model. If Groq later deprecates that too, check console.groq.com/docs/models
# and update GROQ_MODEL in .env (no code changes needed).

docker compose up --build
```

- Frontend: http://localhost:8080
- Backend docs: http://localhost:8000/api/docs

## 🛠️ Local development (without Docker)

**Backend**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # then set GROQ_API_KEY
uvicorn app.main:app --reload
```

**Frontend**
```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```
Visit http://localhost:5173. The Vite dev server proxies `/api` to
`http://localhost:8000` automatically.

**Run the test suite**
```bash
cd backend
pytest -v
```

---

## 📁 Project structure

```
documind/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, middleware, startup
│   │   ├── config.py            # env-driven settings
│   │   ├── models.py            # SQLAlchemy: User, Document, ChatSession, ChatMessage
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── security.py          # password hashing, JWT
│   │   ├── deps.py               # get_db, get_current_user
│   │   ├── auth/router.py        # register / login / me
│   │   ├── documents/            # upload, list, delete + extraction/chunking/FAISS
│   │   ├── chat/                 # sessions API + streaming RAG chain
│   │   └── core/                 # logging, rate limiting, exception handlers
│   ├── tests/                    # pytest: auth, multi-tenant isolation, chat
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/                # Login, Register, Workspace
│   │   ├── components/           # DocumentSidebar, ChatMessage
│   │   ├── context/AuthContext.jsx
│   │   └── api.js                 # axios client + SSE streaming fetch
│   └── Dockerfile
├── .github/workflows/ci.yml       # tests + lint + build, on every push
└── docker-compose.yml
```

---

## 🔐 Security notes

- Passwords hashed with bcrypt, never stored or logged in plaintext.
- JWT access tokens, 24h expiry (configurable).
- Every document/chat/session query is scoped by `owner_id` at the ORM
  level — one user's uploads and conversations are structurally
  unreachable by another user (see `tests/test_documents_and_chat.py`).
- Upload validation: extension allowlist, per-file size cap, per-upload
  file count cap, per-account document cap.
- Rate limiting per IP on auth, upload, and chat endpoints (`slowapi`).
- `.env` files are gitignored; `.env.example` documents every variable.

## 📈 What I'd do next (honest roadmap)

Good projects name their own limitations — this is what I'd point to if
asked "what would you improve next":
- Swap FAISS for a shared vector DB (Qdrant or pgvector) to support
  horizontal scaling across multiple backend replicas.
- Alembic migrations instead of `create_all()` for schema changes.
- An answer-confidence indicator based on retrieval similarity scores.
- OAuth (Google) login alongside email/password.
- Celery + Redis for document processing at higher upload volume, instead
  of FastAPI `BackgroundTasks`.

---

## 📄 License

MIT — see `LICENSE`.
