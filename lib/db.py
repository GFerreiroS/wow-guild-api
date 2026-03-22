import os
from datetime import datetime
from enum import Enum
from typing import Generator, Optional

import dotenv
from sqlalchemy import Column, String, inspect
from sqlmodel import Field, Session, SQLModel, create_engine

dotenv.load_dotenv()


def _build_database_url() -> str:
    """Return the database URL from the environment.

    In development and tests the Postgres variables might not be defined.
    When that happens fall back to a local SQLite database so that Alembic
    and unit tests continue to work without extra configuration.
    """

    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url

    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    database = os.getenv("POSTGRES_DB")

    if all([user, password, host, port, database]):
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"

    # Fallback for local development/testing
    return "sqlite:///./wowguild.db"


DATABASE_URL = _build_database_url()


def _engine_kwargs() -> dict:
    if DATABASE_URL.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


engine = create_engine(DATABASE_URL, echo=False, **_engine_kwargs())


class GuildMember(SQLModel, table=True):
    character_id: int = Field(primary_key=True)
    name: str
    realm: str
    level: int
    race: str
    clazz: str  # `class` is a reserved keyword
    faction: str
    rank: int
    fetched_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")


class User(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password: str
    role: str
    created_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


class OAuthToken(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    access_token: str
    expires_at: float


class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    # foreign key to the user who created it
    created_by: int = Field(foreign_key="user.id")


class SignUpStatus(str, Enum):
    Assist = "Assist"
    Late = "Late"
    Tentative = "Tentative"
    Absence = "Absence"


class EventSignUp(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="event.id")
    user_id: int = Field(foreign_key="user.id")
    signed_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())
    status: SignUpStatus = Field(
        default=SignUpStatus.Assist,  # default at Python level
        sa_column=Column(String, server_default=SignUpStatus.Assist.value),
    )


class Expansion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True)


class Instance(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    blizzard_id: int = Field(unique=True)
    expansion_id: int = Field(foreign_key="expansion.id")
    name: str
    description: Optional[str] = None
    img: Optional[str] = None
    instance_type: str  # "raid" or "dungeon"
    is_current_season: bool = Field(default=False)
    sort_order: int = Field(default=0)


class Encounter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    blizzard_id: int
    instance_id: int = Field(foreign_key="instance.id")
    name: str
    description: Optional[str] = None
    creature_display_id: Optional[int] = None
    img: Optional[str] = None
    sort_order: int = Field(default=0)


def reset_db():
    """
    Drops all tables and recreates them from the current models.
    """
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def dispose_db():
    engine.dispose()


def get_session() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependencies."""

    with Session(engine) as session:
        yield session


def table_exists(table_name: str) -> bool:
    """Utility used by migrations/tests to check for tables."""

    inspector = inspect(engine)
    return table_name in inspector.get_table_names()
