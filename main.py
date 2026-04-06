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
import lib.instances as instances
import lib.schemas as schema
import lib.security as security
import lib.updater as updater
import lib.wow as wow
from lib.admin import setup_admin
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
    if os.getenv("INSTANCE_BACKEND", "yaml").lower() == "db":
        with db.Session(db.engine) as session:
            if instances.is_db_empty(session):
                logger.info("Instance DB empty — auto-seeding from YAML.")
                instances.seed_from_yaml(session)
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
    tags=["Auth"],
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
    tags=["Auth"],
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
@api_app.get("/token", summary="Read the current WoW token price in gold", tags=["WoW"])
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


@api_app.get("/guild", summary="Read guild info from Blizzard", tags=["Guild"])
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
@api_app.get("/guild/roster", summary="Read cached guild roster from Postgres", tags=["Guild"])
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


def _do_update_roster(session: Session) -> dict:
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


@api_app.post(
    "/guild/roster/update",
    summary="Fetch from Blizzard and upsert into Postgres",
    tags=["Guild"],
)
def update_roster(
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(
        session, current_user, required_roles={"owner", "administrator"}
    )
    return _do_update_roster(session)


@api_app.get("/guild/roster/{character_id}", summary="Get a single character by ID", tags=["Guild"])
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
    tags=["Users"],
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
    tags=["Users"],
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
    "/admin/db/init",
    summary="Create database tables if they don't exist yet",
    tags=["Admin"],
)
def init_database():
    """Creates all tables. Safe to call multiple times — skips existing tables."""
    return db.init_db()


@api_app.post(
    "/admin/db/reset",
    dependencies=[Depends(security.require_roles("owner"))],
    summary="Drop & recreate all tables (dev only!)",
    tags=["Admin"],
)
def reset_database():
    """WARNING: drops and recreates ALL tables."""
    db.reset_db()
    logger.warning("Database reset by owner.")
    return {"status": "ok"}


@api_app.post(
    "/admin/db/populate",
    summary="Fetch roster and guild info from Blizzard and update the database",
    tags=["Admin"],
)
def populate_database(
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(
        session, current_user, required_roles={"owner", "administrator"}
    )
    roster_result = _do_update_roster(session)
    _get_guild_info_cached()
    return {"status": "ok", "roster": roster_result}


@api_app.post(
    "/admin/db/seed-dev-user",
    summary="Create dev seed user linked to Lapaella (dev only!)",
    tags=["Admin"],
)
def seed_dev_user(
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(
        session, current_user, required_roles={"owner", "administrator"}
    )
    gm = session.exec(
        select(db.GuildMember).where(db.GuildMember.name == "Lapaella")
    ).first()
    if not gm:
        raise HTTPException(status_code=404, detail="Character Lapaella not found — run /admin/db/populate first")

    _create_user_record(
        schema.UserCreate(
            username="paella",
            password="Paella1.",
            character_id=gm.character_id,
        ),
        session=session,
    )
    return {"status": "ok", "username": "paella"}


# ---------------------------------------------------------------------------
# Instance endpoints
# ---------------------------------------------------------------------------
@api_app.get(
    "/instances",
    response_model=list[schema.InstanceRead],
    summary="List instances filtered by expansion, type, or current season",
    tags=["Instances"],
)
def list_instances(
    expansion: Optional[str] = Query(None, description="Expansion name, e.g. 'The War Within'"),
    type: Optional[str] = Query(None, pattern="^(raid|dungeon)$"),
    current_season: bool = Query(False),
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(session, current_user)
    return instances.get_instances(session, expansion, type, current_season)


@api_app.get(
    "/instances/{blizzard_id}",
    response_model=schema.InstanceDetailRead,
    summary="Get a single instance with its encounters",
    tags=["Instances"],
)
def get_instance(
    blizzard_id: int,
    session: Session = Depends(db.get_session),
    current_user: Optional[db.User] = Depends(security.get_optional_user),
):
    security.ensure_authenticated_or_bootstrap(session, current_user)
    inst = instances.get_instance(session, blizzard_id)
    if not inst:
        raise HTTPException(404, "Instance not found")
    return inst


@api_app.post(
    "/admin/instances/seed",
    dependencies=[Depends(security.require_roles("owner"))],
    summary="Seed instance DB from YAML files (requires INSTANCE_BACKEND=db)",
    tags=["Admin"],
)
def seed_instances(session: Session = Depends(db.get_session)):
    if os.getenv("INSTANCE_BACKEND", "yaml").lower() != "db":
        raise HTTPException(400, "INSTANCE_BACKEND is not set to 'db'")
    return instances.seed_from_yaml(session)


# ---------------------------------------------------------------------------
# Update endpoints
# ---------------------------------------------------------------------------
@api_app.get(
    "/admin/updates/check",
    response_model=schema.UpdateCheckResponse,
    dependencies=[Depends(security.require_roles("owner", "administrator"))],
    summary="Check if a new version is available on GitHub",
    tags=["Admin"],
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
    tags=["Admin"],
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
    tags=["Events"],
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
    tags=["Events"],
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
    tags=["Events"],
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
    tags=["Events"],
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
    tags=["Events"],
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
    tags=["Events"],
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
    tags=["Events"],
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
    tags=["Events"],
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
    tags=["Events"],
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
setup_admin(app)
