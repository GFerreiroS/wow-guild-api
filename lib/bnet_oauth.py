"""Battle.net OAuth2 — authorization code flow + user profile API."""

from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

BNET_AUTH_URL = "https://oauth.battle.net/authorize"
BNET_TOKEN_URL = "https://oauth.battle.net/token"
BNET_USERINFO_URL = "https://oauth.battle.net/userinfo"

# In-memory CSRF state store: token -> {expiry, next_url}
_states: dict[str, dict] = {}
_STATE_TTL = 300  # seconds


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _client_id() -> str:
    v = os.getenv("CLIENT_ID")
    if not v:
        raise RuntimeError("CLIENT_ID env var not set")
    return v


def _client_secret() -> str:
    v = os.getenv("CLIENT_SECRET")
    if not v:
        raise RuntimeError("CLIENT_SECRET env var not set")
    return v


def _redirect_uri() -> str:
    return os.getenv(
        "BNET_CALLBACK_URL", "http://localhost:8000/api/auth/bnet/callback"
    )


def _region() -> str:
    return os.getenv("REGION", "eu")


def _locale() -> str:
    return os.getenv("LOCALE", "en_US")


# ---------------------------------------------------------------------------
# State / CSRF
# ---------------------------------------------------------------------------

def generate_state(next_url: Optional[str] = None) -> str:
    """Generate a CSRF state token and stash the optional redirect destination."""
    state = secrets.token_urlsafe(32)
    _states[state] = {"expiry": time.time() + _STATE_TTL, "next": next_url}
    return state


def consume_state(state: str) -> Optional[dict]:
    """Validate and remove a state token. Returns payload or None if invalid/expired."""
    data = _states.pop(state, None)
    if data is None or time.time() > data["expiry"]:
        return None
    return data


# ---------------------------------------------------------------------------
# OAuth flow
# ---------------------------------------------------------------------------

def get_authorization_url(state: str) -> str:
    params = {
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "wow.profile openid",
        "state": state,
    }
    return BNET_AUTH_URL + "?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict:
    """Exchange authorization code for a user access token."""
    import base64

    credentials = base64.b64encode(
        f"{_client_id()}:{_client_secret()}".encode()
    ).decode()
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri(),
        }
    ).encode()
    req = urllib.request.Request(
        BNET_TOKEN_URL,
        data=data,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"BNet token exchange failed ({e.code}): {e.read().decode()}")


# ---------------------------------------------------------------------------
# Profile API
# ---------------------------------------------------------------------------

def get_user_info(access_token: str) -> dict:
    """GET /userinfo — returns sub (BNet account ID) and battletag."""
    req = urllib.request.Request(
        BNET_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_wow_profile(access_token: str) -> list[dict]:
    """Return all WoW characters on this BNet account (all sub-accounts flattened)."""
    region = _region()
    locale = _locale()
    url = (
        f"https://{region}.api.blizzard.com/profile/user/wow?"
        + urllib.parse.urlencode({"namespace": f"profile-{region}", "locale": locale})
    )
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {access_token}"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError:
        return []

    characters: list[dict] = []
    for account in data.get("wow_accounts", []):
        for char in account.get("characters", []):
            characters.append(
                {
                    "id": char["id"],
                    "name": char["name"],
                    "realm": char.get("realm", {}).get("slug", ""),
                    "level": char.get("level", 0),
                }
            )
    return characters
