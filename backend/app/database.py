from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    """Create tables if they don't exist.

    For a real production system you'd use Alembic migrations instead of
    create_all(); this project ships an `alembic/` folder stub (see README)
    documenting how that upgrade path works, but create_all keeps the demo
    zero-config.
    """
    from app import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)
