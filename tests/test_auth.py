"""Tests for /auth endpoints."""

from tests.conftest import auth_headers, make_user


def test_login_success(client, session):
    make_user(session)
    resp = client.post("/api/auth/token", data={"username": "testuser", "password": "Test1234!"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client, session):
    make_user(session)
    resp = client.post("/api/auth/token", data={"username": "testuser", "password": "wrong"})
    assert resp.status_code == 401


def test_login_unknown_user(client, session):
    make_user(session)
    resp = client.post("/api/auth/token", data={"username": "nobody", "password": "Test1234!"})
    assert resp.status_code == 401


def test_me(client, session):
    make_user(session)
    resp = client.get("/api/auth/me", headers=auth_headers(client))
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testuser"
    assert data["role"] == "user"


def test_me_unauthenticated(client, session):
    make_user(session)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_bad_token(client, session):
    make_user(session)
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer bad.token.here"})
    assert resp.status_code == 401


def test_owner_role(client, session):
    make_user(session, rank=0, username="guildmaster")
    resp = client.get("/api/auth/me", headers=auth_headers(client, "guildmaster"))
    assert resp.json()["role"] == "owner"


def test_admin_role(client, session):
    make_user(session, rank=1, username="officer")
    resp = client.get("/api/auth/me", headers=auth_headers(client, "officer"))
    assert resp.json()["role"] == "administrator"
