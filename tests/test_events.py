"""Tests for /events endpoints."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import auth_headers, make_user


def _future(hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _event_payload(title: str = "Raid Night", start_offset: int = 1, end_offset: int = 3) -> dict:
    return {
        "title": title,
        "description": "Come prepared",
        "start_time": _future(start_offset),
        "end_time": _future(end_offset),
    }


# ---------------------------------------------------------------------------
# Create / read / update / delete events
# ---------------------------------------------------------------------------

def test_create_event_owner(client, session):
    make_user(session, rank=0, username="owner1")
    resp = client.post("/api/events", json=_event_payload(), headers=auth_headers(client, "owner1"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Raid Night"
    assert data["signups"] == []


def test_create_event_forbidden_for_user(client, session):
    make_user(session, rank=2)
    resp = client.post("/api/events", json=_event_payload(), headers=auth_headers(client))
    assert resp.status_code == 403


def test_create_event_end_before_start(client, session):
    make_user(session, rank=0, username="owner1")
    payload = {
        "title": "Bad Times",
        "start_time": _future(3),
        "end_time": _future(1),
    }
    resp = client.post("/api/events", json=payload, headers=auth_headers(client, "owner1"))
    assert resp.status_code == 422


def test_get_event(client, session):
    make_user(session, rank=0, username="owner1")
    created = client.post("/api/events", json=_event_payload(), headers=auth_headers(client, "owner1")).json()
    event_id = created["id"]

    resp = client.get(f"/api/events/{event_id}", headers=auth_headers(client, "owner1"))
    assert resp.status_code == 200
    assert resp.json()["id"] == event_id


def test_get_event_not_found(client, session):
    make_user(session, rank=0, username="owner1")
    resp = client.get("/api/events/99999", headers=auth_headers(client, "owner1"))
    assert resp.status_code == 404


def test_update_event(client, session):
    make_user(session, rank=0, username="owner1")
    created = client.post("/api/events", json=_event_payload(), headers=auth_headers(client, "owner1")).json()
    event_id = created["id"]

    updated_payload = _event_payload(title="Updated Raid")
    resp = client.put(f"/api/events/{event_id}", json=updated_payload, headers=auth_headers(client, "owner1"))
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated Raid"


def test_delete_event(client, session):
    make_user(session, rank=0, username="owner1")
    created = client.post("/api/events", json=_event_payload(), headers=auth_headers(client, "owner1")).json()
    event_id = created["id"]

    resp = client.delete(f"/api/events/{event_id}", headers=auth_headers(client, "owner1"))
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    resp = client.get(f"/api/events/{event_id}", headers=auth_headers(client, "owner1"))
    assert resp.status_code == 404


def test_list_events(client, session):
    make_user(session, rank=0, username="owner1")
    headers = auth_headers(client, "owner1")
    client.post("/api/events", json=_event_payload("Event A"), headers=headers)
    client.post("/api/events", json=_event_payload("Event B"), headers=headers)

    resp = client.get("/api/events", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_list_events_pagination(client, session):
    make_user(session, rank=0, username="owner1")
    headers = auth_headers(client, "owner1")
    for i in range(5):
        client.post("/api/events", json=_event_payload(f"Event {i}"), headers=headers)

    resp = client.get("/api/events?limit=2", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# Signups: create / update / delete
# ---------------------------------------------------------------------------

def _create_event(client, headers) -> int:
    return client.post("/api/events", json=_event_payload(), headers=headers).json()["id"]


def test_sign_up(client, session):
    owner = make_user(session, rank=0, username="owner1")
    headers = auth_headers(client, "owner1")
    event_id = _create_event(client, headers)

    resp = client.post(
        f"/api/events/{event_id}/sign",
        json={"user_id": owner.id, "status": "Assist"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "owner1"
    assert data["status"] == "Assist"


def test_sign_up_duplicate(client, session):
    owner = make_user(session, rank=0, username="owner1")
    headers = auth_headers(client, "owner1")
    event_id = _create_event(client, headers)

    payload = {"user_id": owner.id, "status": "Assist"}
    client.post(f"/api/events/{event_id}/sign", json=payload, headers=headers)
    resp = client.post(f"/api/events/{event_id}/sign", json=payload, headers=headers)
    assert resp.status_code == 400
    assert "Already signed up" in resp.json()["detail"]


def test_sign_up_other_user_as_regular_forbidden(client, session):
    import lib.db as db_

    user1 = make_user(session, rank=2, username="user1")
    other = make_user(session, rank=2, username="user2", character_id=2)
    headers = auth_headers(client, "user1")

    # Create event directly in the DB (regular users can't use the create endpoint)
    event = db_.Event(
        title="T",
        start_time=datetime.now(timezone.utc) + timedelta(hours=1),
        end_time=datetime.now(timezone.utc) + timedelta(hours=2),
        created_by=user1.id,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    resp = client.post(
        f"/api/events/{event.id}/sign",
        json={"user_id": other.id, "status": "Assist"},
        headers=headers,
    )
    assert resp.status_code == 403


def test_update_signup(client, session):
    owner = make_user(session, rank=0, username="owner1")
    headers = auth_headers(client, "owner1")
    event_id = _create_event(client, headers)

    client.post(
        f"/api/events/{event_id}/sign",
        json={"user_id": owner.id, "status": "Assist"},
        headers=headers,
    )

    resp = client.put(
        f"/api/events/{event_id}/sign",
        json={"user_id": owner.id, "status": "Late"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Late"


def test_delete_signup(client, session):
    owner = make_user(session, rank=0, username="owner1")
    headers = auth_headers(client, "owner1")
    event_id = _create_event(client, headers)

    client.post(
        f"/api/events/{event_id}/sign",
        json={"user_id": owner.id, "status": "Assist"},
        headers=headers,
    )

    resp = client.delete(
        f"/api/events/{event_id}/sign?user_id={owner.id}",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


def test_update_signup_not_found(client, session):
    owner = make_user(session, rank=0, username="owner1")
    headers = auth_headers(client, "owner1")
    event_id = _create_event(client, headers)

    resp = client.put(
        f"/api/events/{event_id}/sign",
        json={"user_id": owner.id, "status": "Late"},
        headers=headers,
    )
    assert resp.status_code == 404


def test_statuses_endpoint(client, session):
    make_user(session, rank=0, username="owner1")
    resp = client.get("/api/event/statuses", headers=auth_headers(client, "owner1"))
    assert resp.status_code == 200
    assert set(resp.json()) == {"Assist", "Late", "Tentative", "Absence"}
