from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


# --- Auth ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# --- Documents ---
class DocumentOut(BaseModel):
    id: str
    filename: str
    extension: str
    size_bytes: int
    status: str
    error_message: str | None = None
    num_chunks: int
    num_pages: int
    created_at: datetime

    class Config:
        from_attributes = True


# --- Chat ---
class ChatSessionCreate(BaseModel):
    title: str | None = "New chat"
    document_ids: list[str] | None = None


class ChatSessionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ChatSessionScopeUpdate(BaseModel):
    # Empty list / null = scope cleared (search across all documents again).
    document_ids: list[str] | None = None


class ChatSessionOut(BaseModel):
    id: str
    title: str
    document_ids: list[str] = []
    created_at: datetime

    class Config:
        from_attributes = True


class SourceRef(BaseModel):
    source: str
    page: int
    snippet: str
    document_id: str | None = None


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    sources: list[SourceRef] = []
    latency_ms: int | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    session_id: str
    question: str = Field(min_length=1, max_length=4000)
