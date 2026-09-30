import io
import time


def test_upload_requires_auth(client):
    files = {"files": ("test.txt", io.BytesIO(b"hello world"), "text/plain")}
    resp = client.post("/api/v1/documents/upload", files=files)
    assert resp.status_code == 401


def test_upload_rejects_unsupported_type(client, auth_headers):
    files = {"files": ("malware.exe", io.BytesIO(b"binary"), "application/octet-stream")}
    resp = client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    assert resp.status_code == 400


def test_upload_txt_and_processes(client, auth_headers):
    content = b"DocuMind AI is a retrieval augmented generation chatbot for documents." * 20
    files = {"files": ("notes.txt", io.BytesIO(content), "text/plain")}
    resp = client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
    assert resp.status_code == 202
    doc = resp.json()[0]
    assert doc["filename"] == "notes.txt"
    assert doc["status"] in ("processing", "ready")

    # background task should finish quickly for a tiny file
    for _ in range(20):
        listing = client.get("/api/v1/documents", headers=auth_headers).json()
        match = next(d for d in listing if d["id"] == doc["id"])
        if match["status"] != "processing":
            break
        time.sleep(0.5)
    assert match["status"] == "ready"
    assert match["num_chunks"] >= 1


def test_list_documents_isolated_per_user(client):
    client.post("/api/v1/auth/register", json={"email": "userA@example.com", "password": "password123"})
    client.post("/api/v1/auth/register", json={"email": "userB@example.com", "password": "password123"})
    token_a = client.post(
        "/api/v1/auth/login", data={"username": "userA@example.com", "password": "password123"}
    ).json()["access_token"]
    token_b = client.post(
        "/api/v1/auth/login", data={"username": "userB@example.com", "password": "password123"}
    ).json()["access_token"]

    files = {"files": ("a.txt", io.BytesIO(b"user A private content"), "text/plain")}
    client.post(
        "/api/v1/documents/upload", files=files, headers={"Authorization": f"Bearer {token_a}"}
    )

    docs_b = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert docs_b == []  # user B must not see user A's documents


def test_create_and_list_chat_session(client, auth_headers):
    resp = client.post("/api/v1/chat/sessions", json={"title": "My session"}, headers=auth_headers)
    assert resp.status_code == 201
    session_id = resp.json()["id"]

    listing = client.get("/api/v1/chat/sessions", headers=auth_headers).json()
    assert any(s["id"] == session_id for s in listing)


def test_chat_session_requires_ownership(client, auth_headers):
    client.post("/api/v1/auth/register", json={"email": "eve@example.com", "password": "password123"})
    token_eve = client.post(
        "/api/v1/auth/login", data={"username": "eve@example.com", "password": "password123"}
    ).json()["access_token"]

    session = client.post("/api/v1/chat/sessions", json={"title": "secret"}, headers=auth_headers).json()

    resp = client.get(
        f"/api/v1/chat/sessions/{session['id']}/messages",
        headers={"Authorization": f"Bearer {token_eve}"},
    )
    assert resp.status_code == 404
