"""
Centralized application configuration.

All values can be overridden via environment variables / .env file, which is
the standard 12-factor approach for production deployments (Docker, Render,
Railway, EC2, etc.) instead of hardcoding secrets in source.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "DocuMind AI"
    ENVIRONMENT: str = "development"  # development | production
    API_V1_PREFIX: str = "/api/v1"

    # --- Security ---
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_STRING"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Database ---
    # Defaults to local SQLite so the project runs with zero extra infra.
    # In production, set DATABASE_URL=postgresql://user:pass@host:5432/db
    DATABASE_URL: str = "sqlite:///./documind.db"

    # --- LLM / Embeddings ---
    GROQ_API_KEY: str = ""
    # Groq deprecated llama-3.1-8b-instant on 2026-08-16; this is its
    # recommended, currently-supported replacement.
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Storage ---
    UPLOAD_DIR: str = "storage/uploads"
    VECTORSTORE_DIR: str = "storage/vectorstores"

    # --- Limits (tuned for a demo/portfolio deployment) ---
    MAX_UPLOAD_MB: int = 20
    MAX_FILES_PER_UPLOAD: int = 10
    MAX_DOCUMENTS_PER_USER: int = 50
    RATE_LIMIT_CHAT: str = "20/minute"
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_UPLOAD: str = "10/minute"

    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    RETRIEVER_K: int = 4

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
