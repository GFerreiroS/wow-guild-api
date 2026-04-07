import logging
import logging.config
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import List, Optional, cast

import urllib.parse

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from sqlalchemy import delete
from sqlmodel import Session, select

import lib.bnet_oauth as bnet_oauth
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
    with db.Session(db.engine) as session:
        if instances.is_db_empty(session):
            if instances.DATA_DIR.exists():
                logger.info("Instance DB empty — auto-seeding from YAML archive.")
                instances.seed_from_yaml(session)
            else:
                logger.info("Instance DB empty and no YAML archive found — run POST /admin/instances/seed after setup.")
    yield
    db.dispose_db()
    logger.info("Application shut down.")


api_app = FastAPI()
api_app.state.limiter = limiter
api_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
api_app.add_middleware(SlowAPIMiddleware)


def _custom_openapi():
    if api_app.openapi_schema:
        return api_app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(title="WoW Guild API", version="1.0.0", routes=api_app.routes)
    schema["servers"] = [{"url": "/api"}]
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }
    for path in schema.get("paths", {}).values():
        for op in path.values():
            if isinstance(op, dict) and "security" in op:
                op["security"] = [{"BearerAuth": []}]
    api_app.openapi_schema = schema
    return schema

api_app.openapi = _custom_openapi


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
        battletag=current_user.bnet_battletag,
        primary_character_id=current_user.primary_character_id,
    )


class _PrimaryCharPayload(BaseModel):
    character_id: int


@api_app.patch(
    "/auth/me/primary-character",
    response_model=schema.UserRead,
    summary="Set the authenticated user's primary character",
    dependencies=[Depends(security.require_authenticated_user)],
    tags=["Auth"],
)
def set_primary_character(
    payload: _PrimaryCharPayload,
    current_user: db.User = Depends(security.get_current_user),
    session: Session = Depends(db.get_session),
):
    member = session.get(db.GuildMember, payload.character_id)
    if not member:
        raise HTTPException(404, "Character not found")
    if member.user_id != current_user.id:
        raise HTTPException(403, "That character does not belong to you")
    current_user.primary_character_id = payload.character_id
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return schema.UserRead(
        id=cast(int, current_user.id),
        username=current_user.username,
        role=current_user.role,
        battletag=current_user.bnet_battletag,
        primary_character_id=current_user.primary_character_id,
    )


# ---------------------------------------------------------------------------
# Battle.net OAuth2 endpoints
# ---------------------------------------------------------------------------

_BNET_TEST_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>BNet Login Test</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', system-ui, monospace; background: #0d1117; color: #c9d1d9; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 2.5rem; max-width: 560px; width: 100%; }
    h1 { font-size: 1.4rem; color: #c79552; margin-bottom: 0.25rem; }
    .sub { color: #8b949e; font-size: 0.85rem; margin-bottom: 2rem; }
    .btn { display: inline-block; background: #1f6feb; color: #fff; padding: .65rem 1.4rem; text-decoration: none; border-radius: 6px; font-size: 0.9rem; font-weight: 600; transition: background .15s; }
    .btn:hover { background: #388bfd; }
    .btn.secondary { background: #21262d; border: 1px solid #30363d; }
    .btn.secondary:hover { background: #30363d; }
    .info-row { display: flex; align-items: center; gap: .6rem; margin-bottom: 1.2rem; }
    .badge { background: #238636; color: #fff; font-size: .75rem; font-weight: 700; padding: .2rem .6rem; border-radius: 20px; }
    .label { color: #8b949e; font-size: .8rem; margin-bottom: .4rem; }
    pre, .token-box { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: .9rem; font-size: .78rem; overflow-x: auto; color: #79c0ff; margin-bottom: 1.2rem; }
    .token-box { word-break: break-all; color: #a5f3c4; }
    .actions { display: flex; gap: .75rem; flex-wrap: wrap; margin-top: 1rem; }
    .error { color: #f85149; background: #1a0c0c; border: 1px solid #f8514950; border-radius: 6px; padding: .75rem 1rem; margin-bottom: 1.2rem; font-size: .9rem; }
  </style>
</head>
<body>
  <div class="card">
    <h1>&#9876; BNet Login Test</h1>
    <p class="sub">Verifies the Battle.net OAuth2 flow end-to-end.</p>
    <div id="app">
      <a class="btn" href="/api/auth/bnet/login?next=/api/auth/bnet/test">Login with Battle.net</a>
    </div>
  </div>
  <script>
    const p = new URLSearchParams(location.search);
    const token = p.get('token'), tag = p.get('battletag'), err = p.get('error');
    const app = document.getElementById('app');
    if (err) {
      app.innerHTML = `<div class="error">&#10060; ${err}</div><a class="btn secondary" href="/api/auth/bnet/test">Try again</a>`;
    } else if (token) {
      let payload = {};
      try { payload = JSON.parse(atob(token.split('.')[1])); } catch {}
      app.innerHTML = `
        <div class="info-row"><span class="badge">&#10003; Authenticated</span><strong>${tag}</strong></div>
        <div class="label">JWT payload</div>
        <pre>${JSON.stringify(payload, null, 2)}</pre>
        <div class="label">Access token &mdash; paste into Swagger UI Authorize</div>
        <div class="token-box">${token}</div>
        <div class="actions">
          <a class="btn" href="/api/docs">Open Swagger UI</a>
          <a class="btn secondary" href="/api/auth/bnet/test">Reset</a>
        </div>`;
    }
  </script>
</body>
</html>"""


@api_app.get("/auth/bnet/test", include_in_schema=False)
def bnet_test_page():
    return HTMLResponse(_BNET_TEST_PAGE)


@api_app.get(
    "/auth/bnet/login",
    summary="Redirect to Battle.net OAuth2 authorization",
    tags=["Auth"],
)
def bnet_login(next: Optional[str] = Query(None, description="URL to redirect to after login")):
    state = bnet_oauth.generate_state(next_url=next)
    return RedirectResponse(bnet_oauth.get_authorization_url(state))


@api_app.get(
    "/auth/bnet/callback",
    response_model=schema.BNetLoginResponse,
    summary="Battle.net OAuth2 callback — exchanges code for JWT",
    tags=["Auth"],
)
@limiter.limit("10/minute")
def bnet_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    session: Session = Depends(db.get_session),
):
    if error:
        return RedirectResponse(
            f"/api/auth/bnet/test?error={urllib.parse.quote(error)}"
        )

    if not code or not state:
        raise HTTPException(400, "Missing code or state")

    state_data = bnet_oauth.consume_state(state)
    if state_data is None:
        raise HTTPException(400, "Invalid or expired OAuth state — please try logging in again")

    next_url: Optional[str] = state_data.get("next")

    try:
        token_data = bnet_oauth.exchange_code(code)
        user_access_token = token_data["access_token"]

        user_info = bnet_oauth.get_user_info(user_access_token)
        bnet_sub = str(user_info["sub"])
        battletag: str = user_info.get("battletag", bnet_sub)

        wow_chars = bnet_oauth.get_wow_profile(user_access_token)
        char_ids = {c["id"] for c in wow_chars}

        guild_chars = session.exec(
            select(db.GuildMember).where(db.GuildMember.character_id.in_(char_ids))
        ).all()

        if not guild_chars:
            msg = "None of your WoW characters are in this guild"
            if next_url:
                return RedirectResponse(
                    f"{next_url}?error={urllib.parse.quote(msg)}"
                )
            raise HTTPException(403, msg)

        user = session.exec(
            select(db.User).where(db.User.bnet_id == bnet_sub)
        ).first()
        is_first = not security.users_exist(session)

        if user is None:
            best_rank = min(c.rank for c in guild_chars)
            if is_first or best_rank == 0:
                role = "owner"
            elif best_rank == 1:
                role = "administrator"
            else:
                role = "user"
            username = battletag.replace("#", "-")
            if session.exec(
                select(db.User).where(db.User.username == username)
            ).first():
                username = f"{username}-{bnet_sub[-4:]}"

            user = db.User(
                username=username,
                bnet_id=bnet_sub,
                bnet_battletag=battletag,
                role=role,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info("Created BNet user '%s' (role: %s).", username, role)
        else:
            # Refresh battletag in case it changed
            user.bnet_battletag = battletag
            session.add(user)

        for gm in guild_chars:
            if gm.user_id is None or gm.user_id == user.id:
                gm.user_id = user.id
                session.add(gm)

        if user.primary_character_id is None and guild_chars:
            user.primary_character_id = min(guild_chars, key=lambda c: c.rank).character_id
            session.add(user)

        session.commit()

        jwt_token = security.create_access_token(subject=user.username)

        if next_url:
            qs = urllib.parse.urlencode({"token": jwt_token, "battletag": battletag})
            sep = "&" if "?" in next_url else "?"
            return RedirectResponse(f"{next_url}{sep}{qs}")

        return schema.BNetLoginResponse(
            access_token=jwt_token,
            battletag=battletag,
            role=user.role,
            username=user.username,
        )

    except RuntimeError as e:
        logger.error("BNet callback error: %s", e)
        if next_url:
            return RedirectResponse(
                f"{next_url}?error={urllib.parse.quote(str(e))}"
            )
        raise HTTPException(502, str(e))


# ---------------------------------------------------------------------------
# WoW data endpoints
# ---------------------------------------------------------------------------
@api_app.get("/token", summary="Read the current WoW token price in gold", tags=["WoW"])
@limiter.limit("30/minute")
def read_token(
    request: Request,
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
@limiter.limit("15/minute")
def read_guild(
    request: Request,
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
    incoming_ids = {m["id"] for m in roster}

    # Null out primary_character_id for users whose main is leaving the guild
    leaving = session.exec(
        select(db.GuildMember).where(db.GuildMember.character_id.not_in(incoming_ids))
    ).all()
    leaving_ids = {gm.character_id for gm in leaving}
    if leaving_ids:
        affected_users = session.exec(
            select(db.User).where(db.User.primary_character_id.in_(leaving_ids))
        ).all()
        for user in affected_users:
            user.primary_character_id = None
            session.add(user)
        session.commit()

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

    # First user ever always becomes owner regardless of requested role.
    role = "owner" if not security.users_exist(session) else payload.role

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
    char_ids = [u.primary_character_id for u in users if u.primary_character_id is not None]
    chars: dict[int, db.GuildMember] = {}
    if char_ids:
        chars = {
            m.character_id: m
            for m in session.exec(
                select(db.GuildMember).where(db.GuildMember.character_id.in_(char_ids))
            ).all()
        }
    return [
        schema.UserRead(
            id=cast(int, u.id),
            username=u.username,
            role=u.role,
            battletag=u.bnet_battletag,
            primary_character_id=u.primary_character_id,
            primary_character_name=chars[u.primary_character_id].name if u.primary_character_id and u.primary_character_id in chars else None,
            primary_character_class=chars[u.primary_character_id].clazz if u.primary_character_id and u.primary_character_id in chars else None,
        )
        for u in users
    ]


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------
@api_app.post(
    "/admin/db/create-maintainer",
    response_model=schema.UserRead,
    summary="Bootstrap-only: create a maintainer account with username/password (no BNet required)",
    tags=["Admin"],
)
def create_maintainer(
    payload: schema.MaintainerCreate,
    session: Session = Depends(db.get_session),
):
    """Creates an owner account with username/password login. Only works when no users exist."""
    if security.users_exist(session):
        raise HTTPException(
            403, "Maintainer can only be created during bootstrap (before any users exist)"
        )
    existing = session.exec(
        select(db.User).where(db.User.username == payload.username)
    ).first()
    if existing:
        raise HTTPException(400, f"Username '{payload.username}' is already taken")

    err = validate_password(payload.password)
    if err:
        raise HTTPException(400, err)

    hashed = security.get_password_hash(payload.password)
    user = db.User(username=payload.username, password=hashed, role="owner")
    session.add(user)
    session.commit()
    session.refresh(user)
    logger.info("Maintainer account '%s' created.", user.username)
    return schema.UserRead(id=cast(int, user.id), username=user.username, role=user.role)


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
    dependencies=[Depends(security.require_roles("owner", "administrator"))],
    summary="Fetch raids from Blizzard, archive to YAML, and seed the instance DB",
    tags=["Admin"],
)
def seed_instances(
    session: Session = Depends(db.get_session),
    expansion_id: Optional[int] = Query(None, description="Only fetch this journal-expansion ID"),
    current_season: bool = Query(True, description="Include current season raids"),
):
    import lib.blizzard_journal as journal
    raids = journal.generate_raids(
        expansion_id=expansion_id,
        include_current_season=current_season,
    )
    journal.write_raids_yaml(raids)
    return instances.seed_from_data(session, raids, journal.CURRENT_SEASON_RAID_IDS)


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
    try:
        return updater.apply_update()
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
