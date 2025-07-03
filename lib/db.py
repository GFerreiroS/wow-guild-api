import os
from datetime import datetime

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


class OAuthToken(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    access_token: str
    expires_at: float


def init_db():
    SQLModel.metadata.create_all(engine)


def dispose_db():
    engine.dispose()
