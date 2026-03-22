import logging
import logging.config
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import List, Optional, cast

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import delete
from sqlmodel import Session, select

import lib.db as db
import lib.events as events
import lib.guild as guild
import lib.schemas as schema
import lib.security as security
import lib.updater as updater
import lib.wow as wow
from lib.cache import ttl_cache

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# Cached Blizzard helpers (avoid hitting the API on every request)
# ---------------------------------------------------------------------------
@ttl_cache(ttl_seconds=300, key="wow_token")
def _get_wow_token_cached() -> str:
    return wow.get_wow_token()


@ttl_cache(ttl_seconds=3600, key="guild_info")
def _get_guild_info_cached() -> dict:
    return guild.get_guild_info()


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    security.check_config()
    logger.info("Application starting up.")
    try:
        info = updater.check_for_updates()
        if info["update_available"]:
            logger.warning(
                "New version available: %s (running %s). "
                "Call POST /api/admin/updates/apply to update.",
                info["latest_version"],
                info["current_version"],
            )
    except Exception as e:
        logger.debug("Could not check for updates on startup: %s", e)
    yield
    db.dispose_db()
    logger.info("Application shut down.")


api_app = FastAPI()
api_app.state.limiter = limiter
api_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
api_app.add_middleware(SlowAPIMiddleware)


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
def validate_password(passwd: str) -> Optional[str]:
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


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------
@api_app.post(
    "/auth/token",
    response_model=schema.Token,
    summary="Obtain a JWT access token",
)
@limiter.limit(lambda: os.getenv("RATE_LIMIT_LOGIN", "10/minute"))
def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(db.get_session),
):
    user = security.authenticate_user(form_data.username, form_data.password, session)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    access_token = security.create_access_token(subject=user.username)
    return schema.Token(access_token=access_token, token_type="bearer")


@api_app.get(
    "/auth/me",
    response_model=schema.UserRead,
    summary="Return the authenticated user's profile",
    dependencies=[Depends(security.require_authenticated_user)],
)
def read_current_user(
    current_user: db.User = Depends(security.get_current_user),
):
    return schema.UserRead(
        id=cast(int, current_user.id),
        username=current_user.username,
        role=current_user.role,
    )


# ---------------------------------------------------------------------------
# WoW data endpoints
# ---------------------------------------------------------------------------
@api_app.get("/token", summary="Read the current WoW token price in gold")
def read_token(
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(session, current_user)
    try:
        price_copper = int(_get_wow_token_cached())
        price_gold = price_copper // 10000
        return {"price": f"{price_gold:,}"}
    except Exception as e:
        raise HTTPException(502, str(e))


@api_app.get("/guild", summary="Read guild info from Blizzard")
def read_guild(
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(session, current_user)
    try:
        return _get_guild_info_cached()
    except Exception as e:
        raise HTTPException(502, str(e))


# ---------------------------------------------------------------------------
# Guild roster endpoints
# ---------------------------------------------------------------------------
@api_app.get("/guild/roster", summary="Read cached guild roster from Postgres")
def read_roster(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(session, current_user)
    rows = session.exec(select(db.GuildMember).offset(skip).limit(limit)).all()
    return {
        "roster": [r.model_dump() for r in rows],
        "count": len(rows),
        "fetched_at": datetime.now().astimezone(),
    }


@api_app.post(
    "/guild/roster/update",
    summary="Fetch from Blizzard and upsert into Postgres",
)
def update_roster(
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(
        session, current_user, required_roles={"owner", "administrator"}
    )

    result = guild.get_guild_roster()
    roster = result["roster"]

    session.execute(delete(db.GuildMember))
    session.commit()

    for m in roster:
        session.add(
            db.GuildMember(
                character_id=m["id"],
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
    logger.info("Roster updated: %d members.", len(roster))
    return {"count": len(roster), "updated": datetime.now().astimezone()}


@api_app.get("/guild/roster/{character_id}", summary="Get a single character by ID")
def get_roster_id(
    character_id: int,
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(session, current_user)
    member = session.get(db.GuildMember, character_id)
    if not member:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"character": member.model_dump()}


# ---------------------------------------------------------------------------
# User management endpoints
# ---------------------------------------------------------------------------
def _create_user_record(payload: schema.UserCreate, session: Session) -> db.User:
    gm = session.get(db.GuildMember, payload.character_id)
    if not gm:
        raise HTTPException(404, "Character not found")

    existing_user = session.exec(
        select(db.User).where(db.User.username == payload.username)
    ).first()
    if existing_user:
        raise HTTPException(400, f"Username '{payload.username}' is already registered")

    if gm.user_id is not None:
        raise HTTPException(400, "Character already linked to a user")

    err = validate_password(payload.password)
    if err:
        raise HTTPException(400, err)

    if gm.rank == 0:
        role = "owner"
    elif gm.rank == 1:
        role = "administrator"
    else:
        role = "user"

    hashed = security.get_password_hash(payload.password)
    user = db.User(username=payload.username, password=hashed, role=role)
    session.add(user)
    session.commit()
    session.refresh(user)

    gm.user_id = user.id
    session.add(gm)
    session.commit()
    session.refresh(gm)

    logger.info("Created user '%s' with role '%s'.", user.username, user.role)
    return user


@api_app.post(
    "/users",
    response_model=schema.UserRead,
    summary="Create a user and link to a guild character",
)
def create_user(
    payload: schema.UserCreate,
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(
        session, current_user, required_roles={"owner", "administrator"}
    )
    user = _create_user_record(payload, session)
    assert user.id is not None, "New user must have an ID"
    return schema.UserRead(id=user.id, username=user.username, role=user.role)


@api_app.get(
    "/users",
    dependencies=[Depends(security.require_roles("owner", "administrator"))],
    response_model=list[schema.UserRead],
)
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(db.get_session),
):
    users = session.exec(select(db.User).offset(skip).limit(limit)).all()
    return [
        schema.UserRead(id=cast(int, u.id), username=u.username, role=u.role)
        for u in users
    ]


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------
@api_app.post(
    "/admin/db/reset",
    dependencies=[Depends(security.require_roles("owner"))],
    summary="Drop & recreate all tables (dev only!)",
)
def reset_database():
    """WARNING: drops and recreates ALL tables."""
    db.reset_db()
    logger.warning("Database reset by owner.")
    return {"status": "ok"}


@api_app.post(
    "/admin/db/populate",
    dependencies=[Depends(security.require_roles("owner"))],
    summary="Populates database (dev only!)",
)
def populate_database(session: Session = Depends(db.get_session)):
    """Refresh roster, token & guild info; create dev seed user."""
    update_roster(session)
    _get_guild_info_cached()

    gm = session.exec(
        select(db.GuildMember).where(db.GuildMember.name == "Lapaella")
    ).first()
    if not gm:
        raise HTTPException(status_code=404, detail="Character Lapaella not found")

    _create_user_record(
        schema.UserCreate(
            username="paella",
            password="Paella1.",
            character_id=gm.character_id,
        ),
        session=session,
    )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Update endpoints
# ---------------------------------------------------------------------------
@api_app.get(
    "/admin/updates/check",
    response_model=schema.UpdateCheckResponse,
    dependencies=[Depends(security.require_roles("owner", "administrator"))],
    summary="Check if a new version is available on GitHub",
)
def check_updates():
    try:
        return updater.check_for_updates()
    except Exception as e:
        raise HTTPException(502, str(e))


@api_app.post(
    "/admin/updates/apply",
    response_model=schema.UpdateApplyResponse,
    dependencies=[Depends(security.require_roles("owner"))],
    summary="Pull latest release and restart. Retail mode also regenerates instances.",
)
def apply_update():
    game_mode = os.getenv("GAME_MODE", "retail")
    try:
        return updater.apply_update(game_mode)
    except RuntimeError as e:
        raise HTTPException(500, str(e))


# ---------------------------------------------------------------------------
# Event endpoints
# ---------------------------------------------------------------------------
@api_app.get(
    "/events/{event_id}",
    response_model=schema.EventRead,
    summary="Get a single event by ID",
)
def read_event(
    event_id: int,
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(session, current_user)
    return events.get_event(event_id, session)


@api_app.get(
    "/event/statuses",
    response_model=List[str],
    summary="List all valid signup statuses",
)
def get_event_statuses(
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
) -> List[str]:
    """Returns the four allowed signup statuses as a JSON array of strings."""
    security.ensure_authenticated_or_bootstrap(session, current_user)
    return [s.value for s in schema.SignUpStatus]


@api_app.post(
    "/events",
    response_model=schema.EventRead,
    summary="Create a new event (admin/owner only)",
)
def create_event(
    payload: schema.EventCreate,
    session: Session = Depends(db.get_session),
    current_user: db.User = Depends(security.require_roles("owner", "administrator")),
):
    return events.create_event(payload, session, created_by=cast(int, current_user.id))


@api_app.put(
    "/events/{event_id}",
    response_model=schema.EventRead,
    summary="Edit an existing event (admin/owner only)",
)
def update_event(
    event_id: int,
    payload: schema.EventBase,
    session: Session = Depends(db.get_session),
    _: db.User = Depends(security.require_roles("owner", "administrator")),
):
    return events.update_event(event_id, payload, session)


@api_app.delete(
    "/events/{event_id}",
    summary="Delete an event (admin/owner only)",
)
def delete_event(
    event_id: int,
    session: Session = Depends(db.get_session),
    _: db.User = Depends(security.require_roles("owner", "administrator")),
):
    return events.delete_event(event_id, session)


@api_app.get(
    "/events",
    response_model=list[schema.EventRead],
    summary="List events, filter by day/week/month, optional start date",
)
def list_events(
    period: Optional[str] = Query(
        None,
        pattern="^(day|week|month)$",
        description="Window: next 24h / 7d / 30d",
    ),
    start: Optional[date] = Query(None, description="Start date (YYYY-MM-DD). Defaults to today."),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(session, current_user)
    return events.list_events(period, start, skip, limit, session)


@api_app.post(
    "/events/{event_id}/sign",
    response_model=schema.SignUpRead,
    summary="Sign a user up for an event",
)
def sign_up_event(
    event_id: int,
    payload: schema.SignUpCreate,
    session: Session = Depends(db.get_session),
    current_user: db.User = Depends(security.require_authenticated_user),
):
    return events.sign_up_event(event_id, payload, session, actor=current_user)


@api_app.put(
    "/events/{event_id}/sign",
    response_model=schema.SignUpRead,
    summary="Update a signup status for an event",
)
def update_sign_up(
    event_id: int,
    payload: schema.SignUpUpdate,
    session: Session = Depends(db.get_session),
    current_user: db.User = Depends(security.require_authenticated_user),
):
    return events.update_signup(event_id, payload, session, actor=current_user)


@api_app.delete(
    "/events/{event_id}/sign",
    summary="Remove a signup from an event",
)
def delete_sign_up(
    event_id: int,
    user_id: int = Query(..., description="ID of the user to unsign"),
    session: Session = Depends(db.get_session),
    current_user: db.User = Depends(security.require_authenticated_user),
):
    return events.delete_signup(event_id, user_id, session, actor=current_user)


# ---------------------------------------------------------------------------
# Root app with CORS
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Blizzard API",
    description="A simple API to fetch data from Blizzard's API using OAuth2.",
    version="1.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

_cors_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/api", api_app)
