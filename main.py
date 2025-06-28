from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from sqlmodel import Session, select, text

import lib.db as db
import lib.guild as guild
import lib.wow as wow
from lib.security import get_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
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


@app.get("/token")
def read_token():
    price_copper = int(wow.get_wow_token())
    price_gold = price_copper // 10000
    try:
        return {"price": f"{price_gold:,}"}
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/guild")
def read_guild():
    try:
        return guild.get_guild_info()
    except Exception as e:
        raise HTTPException(502, str(e))


@app.get("/guild/roster", summary="Read cached guild roster from Postgres")
def read_roster(session: Session = Depends(get_session)):
    rows = session.exec(select(db.GuildMember)).all()
    return {
        "roster": [r.dict() for r in rows],
        "count": len(rows),
        "fetched_at": datetime.utcnow().isoformat(),
    }


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
