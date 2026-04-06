"""Shared fixtures for all tests.

Sets JWT_SECRET_KEY *before* any imports so lib/security.py captures a valid
secret at module load time and check_config() passes during lifespan startup.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only-32ch")
os.environ["RATE_LIMIT_LOGIN"] = "10000/minute"  # disable effective rate limiting in tests

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import lib.db as db
from main import app, api_app


# ---------------------------------------------------------------------------
# DB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(name="engine")
def engine_fixture():
    _engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(_engine)
    yield _engine
    SQLModel.metadata.drop_all(_engine)


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session):
    def _get_session():
        yield session

    api_app.dependency_overrides[db.get_session] = _get_session
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client
    api_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_guild_member(
    session: Session,
    *,
    character_id: int = 1,
    name: str = "TestChar",
    rank: int = 2,
) -> db.GuildMember:
    gm = db.GuildMember(
        character_id=character_id,
        name=name,
        realm="test-realm",
        level=80,
        race="Human",
        clazz="Warrior",
        faction="ALLIANCE",
        rank=rank,
    )
    session.add(gm)
    session.commit()
    session.refresh(gm)
    return gm


def make_user(
    session: Session,
    *,
    username: str = "testuser",
    password: str = "Test1234!",
    rank: int = 2,
    role: str | None = None,
    character_id: int = 1,
) -> db.User:
    from lib import security

    gm = session.get(db.GuildMember, character_id)
    if not gm:
        gm = make_guild_member(session, character_id=character_id, rank=rank)

    resolved_role = role if role is not None else {0: "owner", 1: "administrator"}.get(rank, "user")
    user = db.User(
        username=username,
        password=security.get_password_hash(password),
        role=resolved_role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    gm.user_id = user.id
    session.add(gm)
    session.commit()
    return user


def get_token(client: TestClient, username: str = "testuser", password: str = "Test1234!") -> str:
    resp = client.post("/api/auth/token", data={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["access_token"]


def auth_headers(client: TestClient, username: str = "testuser", password: str = "Test1234!") -> dict:
    return {"Authorization": f"Bearer {get_token(client, username, password)}"}
