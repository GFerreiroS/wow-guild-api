import base64
from contextlib import asynccontextmanager
from datetime import datetime
from typing import cast

from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import Session, select, text

import lib.admin as admin
import lib.db as db
import lib.guild as guild
import lib.schemas as schema
import lib.wow as wow
from lib.security import get_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    db.dispose_db()


api_app = FastAPI()


def get_session():
    with Session(db.engine) as session:
        yield session


# --------------------------------
# Trivial endpoints
# --------------------------------
@api_app.get("/token", summary="Read the current WoW token price in gold")
def read_token():
    price_copper = int(wow.get_wow_token())
    price_gold = price_copper // 10000
    try:
        return {"price": f"{price_gold:,}"}
    except Exception as e:
        raise HTTPException(502, str(e))


@api_app.get("/guild", summary="Read guild info from Blizzard")
def read_guild():
    try:
        return guild.get_guild_info()
    except Exception as e:
        raise HTTPException(502, str(e))


# --------------------------------
# Guild roster endpoints
# --------------------------------
@api_app.get("/guild/roster", summary="Read cached guild roster from Postgres")
def read_roster(session: Session = Depends(get_session)):
    rows = session.exec(select(db.GuildMember)).all()
    return {
        "roster": [r.dict() for r in rows],
        "count": len(rows),
        "fetched_at": datetime.now().astimezone(),
    }


# Protected
@api_app.post(
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


@api_app.get("/guild/roster/{character_id}", summary="Get a single character by ID")
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
def validate_password(passwd: str):
    if len(passwd) < 8:
        return "Password must be at least 8 characters long"
    if passwd.isalnum():
        return "Password must contain at least one special character"
    if passwd.islower() or passwd.isupper():
        return "Password must contain both uppercase and lowercase letters"
    if passwd.isdigit():
        return "Password must contain at least one letter"
    if not any(ch.isdigit() for ch in passwd):
        return "Password must contain at least one digit"
    return None


@api_app.post(
    "/users",
    response_model=schema.UserRead,
    summary="Create a user and link to a guild character",
)
def create_user(payload: schema.UserCreate, session: Session = Depends(get_session)):
    # 1) Ensure character exists and get its rank
    gm = session.get(db.GuildMember, payload.character_id)
    if not gm:
        raise HTTPException(404, "Character not found")

    username = session.exec(
        select(db.User).where(db.User.username == payload.username)
    ).first()
    if username:
        raise HTTPException(
            status_code=400,
            detail=f"Username '{payload.username}' is already registered",
        )

    err = validate_password(payload.password)
    if err:
        raise HTTPException(400, err)

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
    session.refresh(gm)

    assert user.id is not None, "New user must have an ID"
    return schema.UserRead(id=user.id, username=user.username, role=user.role)


@api_app.get(
    "/users", dependencies=[Depends(get_api_key)], response_model=list[schema.UserRead]
)
def list_users(session: Session = Depends(get_session)):
    users = session.exec(select(db.User)).all()
    return [
        schema.UserRead(id=cast(int, u.id), username=u.username, role=u.role)
        for u in users
    ]


# -----------------------------------
# Admin endpoints
# -----------------------------------


@api_app.post(
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


@api_app.post(
    "/admin/db/populate",
    dependencies=[Depends(get_api_key)],
    summary="Populates database (dev only!)",
)
def populate_database(session: Session = Depends(get_session)):
    """
    WARNING: populates ALL tables by
    1) updating the guild roster in Postgres,
    2) pre-fetching the token,
    3) pre-fetching the guild info.
    """
    # 1) Refresh & store the roster
    update_roster(session)

    # 3) Warm up the guild info cache
    _ = read_guild()

    gm = session.exec(
        select(db.GuildMember).where(db.GuildMember.name == "Lapaella")
    ).first()
    if not gm:
        raise HTTPException(status_code=404, detail="Character Lapaella not found")
    character_id = gm.character_id

    _ = create_user(
        schema.UserCreate(
            username="paella",  # dev user
            password="Paella1.",  # plaintext for dev only
            character_id=character_id,  # must be one of the fetched roster
        ),
        session=session,
    )

    return {"status": "ok"}


app = FastAPI(
    title="Blizzard API",
    description="A simple API to fetch data from Blizzard's API using OAuth2.",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)
app.mount("/api", api_app)
