import os
import sys
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth.router import router as auth_router
from app.chat.router import router as chat_router
from app.config import get_settings
from app.core.exceptions import DocuMindError, documind_error_handler, unhandled_exception_handler
from app.core.logging_config import configure_logging, logger
from app.core.rate_limit import limiter
from app.database import init_db
from app.documents.processing import get_embeddings
from app.documents.router import router as documents_router

settings = get_settings()
configure_logging()

app = FastAPI(
    title=settings.APP_NAME,
    description="Production-grade multi-user RAG chatbot for chatting with your PDF/DOCX/TXT documents.",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_exception_handler(DocuMindError, documind_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(documents_router, prefix=settings.API_V1_PREFIX)
app.include_router(chat_router, prefix=settings.API_V1_PREFIX)


@app.on_event("startup")
def on_startup():
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.VECTORSTORE_DIR, exist_ok=True)
    init_db()

    # In CI / pytest, we must not initialize the sentence-transformers model
    # during application startup because that can trigger slow downloads and
    # flaky network-dependent failures. The embedding layer is loaded lazily on
    # first actual use instead.
    is_test_run = (
        "pytest" in sys.modules
        or os.environ.get("PYTEST_CURRENT_TEST") is not None
        or settings.ENVIRONMENT.lower() == "test"
    )
    if is_test_run:
        logger.info("Skipping embedding warmup in test environment")
        return

    warmup_start = time.time()
    get_embeddings()
    logger.info("Embedding model warmed up in %dms", int((time.time() - warmup_start) * 1000))

    logger.info("DocuMind AI backend started (env=%s)", settings.ENVIRONMENT)
    if not settings.GROQ_API_KEY:
        logger.warning("GROQ_API_KEY is not set — chat requests will fail until it's configured.")


@app.get("/api/health", tags=["health"])
def health_check():
    return {"status": "ok", "app": settings.APP_NAME}
