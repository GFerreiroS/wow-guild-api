import os
from datetime import datetime
from typing import Optional

import dotenv
from sqlmodel import Field, SQLModel, create_engine

dotenv.load_dotenv()

# This will expand using your shell’s env vars (set by you or by a tool like python-dotenv)
DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:"
    f"{os.getenv('POSTGRES_PASSWORD')}@"
    f"{os.getenv('POSTGRES_HOST')}:"
    f"{os.getenv('POSTGRES_PORT')}/"
    f"{os.getenv('POSTGRES_DB')}"
)

engine = create_engine(DATABASE_URL, echo=True)


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


class EventSignUp(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    event_id: int = Field(foreign_key="event.id")
    user_id: int = Field(foreign_key="user.id")
    signed_at: datetime = Field(default_factory=lambda: datetime.now().astimezone())


def reset_db():
    """
    Drops all tables and recreates them from the current models.
    """
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)


def dispose_db():
    engine.dispose()
