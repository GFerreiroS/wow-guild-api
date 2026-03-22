"""Tests for /guild/roster endpoints (DB-backed, no Blizzard API calls)."""

from tests.conftest import auth_headers, make_guild_member, make_user
import lib.db as db


def test_roster_open_when_no_users(client, session):
    """Bootstrap mode: roster is accessible without a token."""
    make_guild_member(session)
    resp = client.get("/api/guild/roster")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1


def test_roster_requires_auth_after_first_user(client, session):
    make_user(session)
    resp = client.get("/api/guild/roster")
    assert resp.status_code == 401


def test_roster_accessible_with_auth(client, session):
    make_user(session)
    resp = client.get("/api/guild/roster", headers=auth_headers(client))
    assert resp.status_code == 200


def test_roster_pagination(client, session):
    for i in range(5):
        make_guild_member(session, character_id=i + 1, name=f"Char{i}")
    make_user(session, character_id=1)

    resp = client.get("/api/guild/roster?limit=2&skip=0", headers=auth_headers(client))
    assert resp.status_code == 200
    assert resp.json()["count"] == 2

    resp2 = client.get("/api/guild/roster?limit=2&skip=2", headers=auth_headers(client))
    assert resp2.status_code == 200
    assert resp2.json()["count"] == 2


def test_get_character_by_id(client, session):
    make_guild_member(session, character_id=42, name="Arthas")
    make_user(session, character_id=42)

    resp = client.get("/api/guild/roster/42", headers=auth_headers(client))
    assert resp.status_code == 200
    assert resp.json()["character"]["name"] == "Arthas"


def test_get_character_not_found(client, session):
    make_user(session)
    resp = client.get("/api/guild/roster/99999", headers=auth_headers(client))
    assert resp.status_code == 404


def test_roster_limit_must_be_positive(client, session):
    make_user(session)
    resp = client.get("/api/guild/roster?limit=0", headers=auth_headers(client))
    assert resp.status_code == 422


def test_roster_limit_max_500(client, session):
    make_user(session)
    resp = client.get("/api/guild/roster?limit=501", headers=auth_headers(client))
    assert resp.status_code == 422
