import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

# Point config at an isolated, throwaway SQLite DB + storage dirs before the
# app module is imported, so tests never touch real dev data.
_tmp_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_dir}/test.db"
os.environ["UPLOAD_DIR"] = os.path.join(_tmp_dir, "uploads")
os.environ["VECTORSTORE_DIR"] = os.path.join(_tmp_dir, "vectorstores")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["GROQ_API_KEY"] = "test-key-not-real"
# The test suite legitimately makes more auth calls per minute than a real
# client should — raise the limits here so we're testing app logic, not
# tripping over the very rate limiter we're verifying exists.
os.environ["RATE_LIMIT_AUTH"] = "1000/minute"
os.environ["RATE_LIMIT_UPLOAD"] = "1000/minute"
os.environ["RATE_LIMIT_CHAT"] = "1000/minute"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib  # noqa: E402
from typing import List  # noqa: E402

from app.documents import processing as processing_module  # noqa: E402


class _FakeEmbeddings:
    """Deterministic, dependency-free stand-in for HuggingFaceEmbeddings.

    Unit tests should exercise our own retrieval/indexing logic, not
    download a real transformer model from the network — that belongs in a
    slower, separately-marked integration test. This hashes text into a
    small fixed-size vector so FAISS similarity search still behaves
    sensibly (identical/similar text -> similar vectors).
    """

    dim = 32

    def _embed(self, text: str) -> List[float]:
        h = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in h[: self.dim]]

    def __call__(self, text):
        # Match the callable interface LangChain vector stores expect from an
        # embeddings provider. Some versions call the object directly instead of
        # only using embed_documents()/embed_query().
        if isinstance(text, str):
            return self.embed_query(text)
        return self.embed_documents(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)


def _fake_get_embeddings():
    return _FakeEmbeddings()


processing_module.get_embeddings.cache_clear()
processing_module.get_embeddings = _fake_get_embeddings  # type: ignore[assignment]

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client):
    email = "test_user@example.com"
    password = "supersecret123"
    client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Test User"})
    resp = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
