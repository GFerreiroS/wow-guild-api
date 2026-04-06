"""Tests for /users endpoints."""

from tests.conftest import auth_headers, make_guild_member, make_user


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

def test_create_user_weak_password_too_short(client, session):
    make_guild_member(session)
    # bootstrap mode — no users yet, endpoint is open
    resp = client.post("/api/users", json={"username": "abc", "password": "Ab1!", "character_id": 1})
    assert resp.status_code == 400
    assert "8 characters" in resp.json()["detail"]


def test_create_user_no_special_char(client, session):
    make_guild_member(session)
    resp = client.post("/api/users", json={"username": "abc", "password": "Abcde123", "character_id": 1})
    assert resp.status_code == 400


def test_create_user_no_digit(client, session):
    make_guild_member(session)
    resp = client.post("/api/users", json={"username": "abc", "password": "Abcdef!!", "character_id": 1})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Bootstrap (first user, no auth required)
# ---------------------------------------------------------------------------

def test_create_first_user_always_owner(client, session):
    """First user created is always owner regardless of requested role."""
    make_guild_member(session)
    resp = client.post(
        "/api/users",
        json={"username": "newuser", "password": "Valid1!!", "character_id": 1, "role": "user"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "newuser"
    assert data["role"] == "owner"


def test_create_user_explicit_role(client, session):
    make_user(session, rank=0, username="owner1")
    make_guild_member(session, character_id=2, name="Officer")

    resp = client.post(
        "/api/users",
        json={"username": "officer1", "password": "Valid1!!", "character_id": 2, "role": "administrator"},
        headers=auth_headers(client, "owner1"),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "administrator"


def test_create_user_invalid_role(client, session):
    make_guild_member(session)
    resp = client.post(
        "/api/users",
        json={"username": "newuser", "password": "Valid1!!", "character_id": 1, "role": "superadmin"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Auth-required after first user exists
# ---------------------------------------------------------------------------

def test_create_user_requires_auth_after_first(client, session):
    make_user(session, rank=0, username="owner1")
    make_guild_member(session, character_id=2, name="AnotherChar")

    resp = client.post(
        "/api/users",
        json={"username": "newuser", "password": "Valid1!!", "character_id": 2},
    )
    assert resp.status_code == 401


def test_create_user_by_owner(client, session):
    make_user(session, rank=0, username="owner1")
    make_guild_member(session, character_id=2, name="AnotherChar")

    resp = client.post(
        "/api/users",
        json={"username": "newuser", "password": "Valid1!!", "character_id": 2},
        headers=auth_headers(client, "owner1"),
    )
    assert resp.status_code == 200


def test_create_user_duplicate_username(client, session):
    make_user(session, rank=0, username="owner1")
    make_guild_member(session, character_id=2, name="AnotherChar")

    client.post(
        "/api/users",
        json={"username": "newuser", "password": "Valid1!!", "character_id": 2},
        headers=auth_headers(client, "owner1"),
    )
    make_guild_member(session, character_id=3, name="YetAnother")
    resp = client.post(
        "/api/users",
        json={"username": "newuser", "password": "Valid1!!", "character_id": 3},
        headers=auth_headers(client, "owner1"),
    )
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"]


def test_list_users_owner_only(client, session):
    make_user(session, rank=0, username="owner1")
    resp = client.get("/api/users", headers=auth_headers(client, "owner1"))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_users_forbidden_for_user(client, session):
    make_user(session, rank=2, username="regular")
    resp = client.get("/api/users", headers=auth_headers(client, "regular"))
    assert resp.status_code == 403


def test_username_min_length(client, session):
    make_guild_member(session)
    resp = client.post(
        "/api/users",
        json={"username": "ab", "password": "Valid1!!", "character_id": 1},
    )
    assert resp.status_code == 422
