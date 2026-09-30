def test_health_check(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_and_login(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "password123", "full_name": "Alice"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert "hashed_password" not in body  # never leak the hash

    resp = client.post("/api/v1/auth/login", data={"username": "alice@example.com", "password": "password123"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_register_duplicate_email_rejected(client):
    client.post("/api/v1/auth/register", json={"email": "bob@example.com", "password": "password123"})
    resp = client.post("/api/v1/auth/register", json={"email": "bob@example.com", "password": "password123"})
    assert resp.status_code == 400


def test_login_wrong_password_rejected(client):
    client.post("/api/v1/auth/register", json={"email": "carol@example.com", "password": "password123"})
    resp = client.post("/api/v1/auth/login", data={"username": "carol@example.com", "password": "wrongpass"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client, auth_headers):
    resp = client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "test_user@example.com"
