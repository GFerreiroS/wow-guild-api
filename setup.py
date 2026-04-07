#!/usr/bin/env python3
"""
WoW Guild API — First-run setup.

Guides you through configuration and bootstraps your database.

Usage:
    python setup.py                   # full setup: configure + bootstrap
    python setup.py --url URL         # bootstrap only against a running server
    python setup.py --reconfigure     # re-run configuration even if .env exists
"""

import argparse
import getpass
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV_FILE = Path(".env")

BLIZZARD_DEV_PORTAL = "https://develop.battle.net/access/clients"

REGIONS = ["eu", "us", "kr", "tw"]
LOCALES = {
    "eu": "en_GB",
    "us": "en_US",
    "kr": "ko_KR",
    "tw": "zh_TW",
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _request(method: str, url: str, data=None, token: str | None = None) -> dict:
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            detail = json.loads(raw).get("detail", raw)
        except Exception:
            detail = raw
        raise RuntimeError(f"HTTP {e.code} {method} {url}\n  {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach {url}\n  {e.reason}")


def _post(base: str, path: str, data=None, token: str | None = None) -> dict:
    return _request("POST", base + path, data=data, token=token)


def _get(base: str, path: str, token: str | None = None) -> dict:
    return _request("GET", base + path, token=token)


def _login(base: str, username: str, password: str) -> str:
    body = urllib.parse.urlencode({"username": username, "password": password}).encode()
    req = urllib.request.Request(
        base + "/auth/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


# ---------------------------------------------------------------------------
# Configuration phase
# ---------------------------------------------------------------------------


def _prompt(label: str, default: str = "", secret: bool = False) -> str:
    if default:
        display = f"{label} [{default}]: "
    else:
        display = f"{label}: "

    while True:
        value = (getpass.getpass(display) if secret else input(display)).strip()
        if value:
            return value
        if default:
            return default
        print("  This field is required.")


def _choose(label: str, choices: list[str], default: str) -> str:
    options = "/".join(f"[{c}]" if c == default else c for c in choices)
    while True:
        value = input(f"{label} ({options}): ").strip().lower() or default
        if value in choices:
            return value
        print(f"  Choose one of: {', '.join(choices)}")


def configure() -> dict:
    print("\n--- Configuration ---\n")
    print("You need a Blizzard developer account to get API credentials.")
    print(f"  Create your client at: {BLIZZARD_DEV_PORTAL}\n")

    client_id = _prompt("Blizzard CLIENT_ID")
    client_secret = _prompt("Blizzard CLIENT_SECRET", secret=True)

    region = _choose("Region", REGIONS, "eu")
    default_locale = LOCALES.get(region, "en_US")
    locale = _prompt("Locale", default=default_locale)

    print()
    guild_name = _prompt("Guild name (display name, e.g. My Guild)")
    guild_slug = _prompt("Guild slug (URL name, e.g. my-guild)")

    print()
    print("Database configuration (press Enter to use Docker Compose defaults):")
    db_user = _prompt("  POSTGRES_USER", default="fastapi")
    db_password = _prompt("  POSTGRES_PASSWORD", default="changeme", secret=True)
    db_name = _prompt("  POSTGRES_DB", default="wowdb")
    db_host = _prompt("  POSTGRES_HOST", default="postgres")
    db_port = _prompt("  POSTGRES_PORT", default="5432")

    jwt_secret = secrets.token_urlsafe(48)
    print(f"\nJWT secret key generated automatically.")
    print(f"  Save this somewhere safe — you'll need it if you ever rotate secrets.")

    allowed_origins = _prompt(
        "\nAllowed frontend origins (comma-separated, or * for dev)",
        default="*",
    )

    github_repo = _prompt(
        "GitHub repo for update checks",
        default="GFerreiroS/wow-guild-api",
    )

    print()
    print("Battle.net OAuth2 — add this URL as an Allowed Redirect URI in your Blizzard app:")
    bnet_callback = _prompt(
        "  BNET_CALLBACK_URL",
        default="http://localhost:8000/api/auth/bnet/callback",
    )

    return {
        "CLIENT_ID": client_id,
        "CLIENT_SECRET": client_secret,
        "REGION": region,
        "LOCALE": locale,
        "GUILD_NAME": guild_name,
        "GUILD_SLUG": guild_slug,
        "POSTGRES_USER": db_user,
        "POSTGRES_PASSWORD": db_password,
        "POSTGRES_DB": db_name,
        "POSTGRES_HOST": db_host,
        "POSTGRES_PORT": db_port,
        "JWT_SECRET_KEY": jwt_secret,
        "ALLOWED_ORIGINS": allowed_origins,
        "GITHUB_REPO": github_repo,
        "BNET_CALLBACK_URL": bnet_callback,
    }


def write_env(config: dict) -> None:
    lines = [
        "# Blizzard API credentials",
        f"CLIENT_ID={config['CLIENT_ID']}",
        f"CLIENT_SECRET={config['CLIENT_SECRET']}",
        "",
        "# Blizzard API region and locale",
        f"REGION={config['REGION']}",
        f"LOCALE={config['LOCALE']}",
        "",
        "# Guild information",
        f"GUILD_NAME={config['GUILD_NAME']}",
        f"GUILD_SLUG={config['GUILD_SLUG']}",
        "",
        "# Database configuration",
        f"POSTGRES_USER={config['POSTGRES_USER']}",
        f"POSTGRES_PASSWORD={config['POSTGRES_PASSWORD']}",
        f"POSTGRES_DB={config['POSTGRES_DB']}",
        f"POSTGRES_HOST={config['POSTGRES_HOST']}",
        f"POSTGRES_PORT={config['POSTGRES_PORT']}",
        "",
        "# JWT configuration",
        f"JWT_SECRET_KEY={config['JWT_SECRET_KEY']}",
        "",
        "# CORS: comma-separated list of allowed frontend origins",
        f"ALLOWED_ORIGINS={config['ALLOWED_ORIGINS']}",
        "",
        "# GitHub repository used for update checks",
        f"GITHUB_REPO={config['GITHUB_REPO']}",
        "",
        "# Battle.net OAuth2 redirect URI (must match Blizzard dev portal)",
        f"BNET_CALLBACK_URL={config['BNET_CALLBACK_URL']}",
        "",
    ]
    ENV_FILE.write_text("\n".join(lines))
    print(f"\n.env written to {ENV_FILE.resolve()}")


# ---------------------------------------------------------------------------
# Wait for server
# ---------------------------------------------------------------------------


def wait_for_server(url: str, timeout: int = 120) -> None:
    print(f"\nWaiting for server at {url} ", end="", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=3)
            print(" ready.")
            return
        except Exception:
            print(".", end="", flush=True)
            time.sleep(3)
    print()
    raise RuntimeError(
        f"Server at {url} did not become ready within {timeout}s.\n"
        "Make sure it is running and reachable."
    )


# ---------------------------------------------------------------------------
# Bootstrap phase
# ---------------------------------------------------------------------------


def step_init_db(base: str) -> None:
    print("\n[1/4] Initialising database...")
    result = _post(base, "/admin/db/init")
    if result.get("status") == "already_exists":
        print("      Tables already exist — skipping.")
    else:
        created = result.get("created", [])
        print(f"      Created: {', '.join(created) if created else 'none'}")


def step_populate(base: str) -> None:
    print("\n[2/4] Fetching guild roster from Blizzard...")
    result = _post(base, "/admin/db/populate")
    count = result.get("roster", {}).get("count", "?")
    print(f"      {count} members loaded.")


def step_create_maintainer(base: str) -> tuple[str, str]:
    print("\n[3/4] Create a maintainer account.")
    print("      This is a hidden owner account for DB maintenance.")
    print("      Regular users will log in via Battle.net instead.\n")

    username = input("      Username: ").strip()
    if not username:
        raise RuntimeError("Username cannot be empty.")

    password = getpass.getpass(
        "      Password (min 8 chars, upper+lower+digit+special): "
    )

    result = _post(
        base,
        "/admin/db/create-maintainer",
        {"username": username, "password": password},
    )
    print(f"      Created '{result['username']}' with role '{result['role']}'.")
    return username, password


def step_seed_instances(base: str, token: str) -> None:
    print("\n[4/4] Seeding raid instance data from Blizzard...")
    print("      This may take a moment...")
    _post(base, "/admin/instances/seed", token=token)
    print("      Done.")


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------

def _has_compose_file() -> bool:
    return any(
        Path(f).exists()
        for f in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
    )


def _maybe_start_docker() -> None:
    if not _has_compose_file():
        print("\nNo docker-compose file found.")
        print("  Start your server manually, then this script will continue.\n")
        return

    print("\nStarting server with docker compose...")
    result = subprocess.run(["docker", "compose", "up", "-d"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  docker compose failed:\n{result.stderr}")
        print("  Start it manually, then the script will continue.\n")
    else:
        print("  Containers started.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="WoW Guild API — first-run setup and bootstrap.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of your running API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--reconfigure",
        action="store_true",
        help="Re-run configuration even if .env already exists",
    )
    args = parser.parse_args()

    base = args.url.rstrip("/") + "/api"
    public_url = args.url.rstrip("/")

    print("\nWoW Guild API — Setup")
    print("=" * 40)

    # Configuration phase
    if not ENV_FILE.exists() or args.reconfigure:
        config = configure()
        write_env(config)
        _maybe_start_docker()
    else:
        print(f"\n.env already exists — skipping configuration. (Use --reconfigure to redo it.)")

    # Wait for server
    wait_for_server(public_url)

    # Bootstrap
    try:
        step_init_db(base)
        step_populate(base)
        username, password = step_create_maintainer(base)

        print("\n      Authenticating...")
        token = _login(base, username, password)

        step_seed_instances(base, token)
    except RuntimeError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    print(f"""
Setup complete!

  API docs:    {public_url}/api/docs
  BNet login:  {public_url}/api/auth/bnet/test
  Maintainer:  {username}  (password login via /api/auth/token)

Next steps:
  - Test Battle.net login at /api/auth/bnet/test
  - Register BNET_CALLBACK_URL in your Blizzard dev portal (Allowed Redirect URIs)
  - Set ALLOWED_ORIGINS to your frontend URL when you deploy the frontend
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
