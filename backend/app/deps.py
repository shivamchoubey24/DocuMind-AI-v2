from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.security import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def get_current_user_for_file(
    request: Request,
    token: str | None = None,
    db: Session = Depends(get_db),
) -> models.User:
    """Same auth as get_current_user, but also accepts the JWT as a ?token=
    query param. Needed because an <iframe>/<a> src can't attach a custom
    Authorization header — only used by the document-file endpoint, never
    for regular API calls, which keep using the header-only dependency."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    auth_header = request.headers.get("Authorization", "")
    raw_token = auth_header.split(" ", 1)[1] if auth_header.lower().startswith("bearer ") else token
    if not raw_token:
        raise credentials_exception
    payload = decode_token(raw_token)
    if payload is None or payload.get("type") != "access":
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user
