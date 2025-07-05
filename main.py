import base64
from contextlib import asynccontextmanager
from datetime import datetime
from typing import cast

from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import Session, select, text

import lib.admin as admin
import lib.db as db
import lib.guild as guild
import lib.wow as wow
from lib.schemas import UserCreate, UserRead
from lib.security import get_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.reset_db()
    yield
    db.dispose_db()


app = FastAPI(
    title="Blizzard API",
    description="A simple API to fetch data from Blizzard's API using OAuth2.",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)


def get_session():
    with Session(db.engine) as session:
        yield session


# --------------------------------
# Trivial endpoints
# --------------------------------
@app.get("/token", summary="Read the current WoW token price in gold")
def read_token():
    price_copper = int(wow.get_wow_token())
    price_gold = price_copper // 10000
    try:
        return {"price": f"{price_gold:,}"}
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/guild", summary="Read guild info from Blizzard")
def read_guild():
    try:
        return guild.get_guild_info()
    except Exception as e:
        raise HTTPException(502, str(e))


# --------------------------------
# Guild roster endpoints
# --------------------------------
@app.get("/guild/roster", summary="Read cached guild roster from Postgres")
def read_roster(session: Session = Depends(get_session)):
    rows = session.exec(select(db.GuildMember)).all()
    return {
        "roster": [r.dict() for r in rows],
        "count": len(rows),
        "fetched_at": datetime.now().astimezone(),
    }


# Protected
@app.post(
    "/guild/roster/update",
    dependencies=[Depends(get_api_key)],
    summary="Fetch from Blizzard and upsert into Postgres",
)
def update_roster(session: Session = Depends(get_session)):
    """
    Protected endpoint: fetch fresh roster via Blizzard API
    and replace all rows in Postgres.
    """
    # 1) Fetch and filter
    result = guild.get_guild_roster()
    roster = result["roster"]

    # 2) Clear out the old table entirely
    t = text("TRUNCATE TABLE guildmember RESTART IDENTITY CASCADE")
    session.execute(t)
    session.commit()

    # 3) Insert fresh data (no guild_slug any more)
    for m in roster:
        session.add(
            db.GuildMember(
                character_id=m.get("id"),
                name=m["name"],
                realm=m["realm"],
                level=m["level"],
                race=m["race"],
                clazz=m["class"],
                faction=m["faction"],
                rank=m["rank"],
                fetched_at=datetime.now().astimezone(),
            )
        )
    session.commit()

    # 4) Return a real timestamp
    return {"count": len(roster), "updated": datetime.now().astimezone()}


@app.get("/guild/roster/{character_id}", summary="Get a single character by ID")
def get_roster_id(session: Session = Depends(get_session), character_id: int = 0):
    rows = session.exec(select(db.GuildMember)).all()
    try:
        character_id = int(character_id)
        if character_id <= 0 or character_id > len(rows):
            raise HTTPException(status_code=400, detail="Invalid character ID")
        else:
            return {
                "character": [r.dict() for r in rows if r.character_id == character_id],
            }
    except Exception as e:
        raise HTTPException(502, str(e))


# ---------------------------------
# User management endpoints
# ---------------------------------
@app.post(
    "/users",
    response_model=UserRead,
    summary="Create a user and link to a guild character",
)
def create_user(payload: UserCreate, session: Session = Depends(get_session)):
    # 1) Ensure character exists and get its rank
    gm = session.get(db.GuildMember, payload.character_id)
    if not gm:
        raise HTTPException(404, "Character not found")

    # 2) Derive role from rank
    if gm.rank == 0:
        role = "owner"
    elif gm.rank == 1:
        role = "administrator"
    else:
        role = "user"

    # 3) Encode password in base64
    hashed = base64.b64encode(payload.password.encode()).decode()

    # 4) Create user
    user = db.User(username=payload.username, password=hashed, role=role)
    session.add(user)
    session.commit()
    session.refresh(user)

    # 5) Link character → user
    gm.user_id = user.id
    session.add(gm)
    session.commit()

    assert user.id is not None, "New user must have an ID"
    return UserRead(id=user.id, username=user.username, role=user.role)


@app.get("/users", response_model=list[UserRead])
def list_users(session: Session = Depends(get_session)):
    users = session.exec(select(db.User)).all()
    return [
        UserRead(id=cast(int, u.id), username=u.username, role=u.role) for u in users
    ]


# -----------------------------------
# Admin endpoints
# -----------------------------------


@app.post(
    "/admin/db/reset",
    dependencies=[Depends(get_api_key)],
    summary="Drop & recreate all tables (dev only!)",
)
def reset_database():
    """
    WARNING: drops and recreates ALL tables
    """
    admin.reset_db()
    return {"status": "ok"}
