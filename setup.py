#!/usr/bin/env python3
"""
Bootstrap script for WoW Guild API.

Run this after your server is up and running to:
  1. Initialise the database
  2. Fetch your guild roster from Blizzard
  3. Create your owner account
  4. Seed raid instance data

Usage:
    python setup.py --url https://your-api-url.com

The server must be running and reachable at the given URL.
Environment variables must already be configured on the server.
"""

import argparse
import getpass
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


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
# Setup steps
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


def step_create_owner(base: str) -> tuple[str, str]:
    print("\n[3/4] Create your owner account.")
    print("      This will be the first user and will have full admin access.\n")

    roster = _get(base, "/guild/roster?limit=500")
    members = roster.get("roster", [])
    if not members:
        raise RuntimeError("Roster is empty. Make sure step 2 completed successfully.")

    print("      Guild members:")
    for i, m in enumerate(members, 1):
        print(f"        {i:3}. {m['name']} ({m['realm']}) — rank {m['rank']}")

    while True:
        try:
            raw = input("\n      Enter the number of your character: ").strip()
            choice = int(raw)
            if 1 <= choice <= len(members):
                character = members[choice - 1]
                break
        except (ValueError, EOFError):
            pass
        print("      Invalid choice, try again.")

    print()
    username = input("      Username: ").strip()
    if not username:
        raise RuntimeError("Username cannot be empty.")

    password = getpass.getpass("      Password (min 8 chars, upper+lower+digit+special): ")

    result = _post(base, "/users", {
        "username": username,
        "password": password,
        "character_id": character["character_id"],
        "role": "owner",
    })
    print(f"      Created '{result['username']}' with role '{result['role']}'.")
    return username, password


def step_seed_instances(base: str, token: str) -> None:
    print("\n[4/4] Seeding raid instance data from Blizzard...")
    print("      This may take a moment...")
    _post(base, "/admin/instances/seed", token=token)
    print("      Done.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap the WoW Guild API after first deploy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Base URL of your running API, e.g. https://my-guild.com or http://localhost:8000",
    )
    args = parser.parse_args()

    base = args.url.rstrip("/") + "/api"
    public_url = args.url.rstrip("/")

    print(f"\nWoW Guild API — Setup")
    print(f"Connecting to {base} ...")

    # Quick connectivity check
    try:
        _get(base.replace("/api", ""), "/api/docs")
    except RuntimeError:
        pass  # /docs might redirect — not critical, we'll fail on actual calls if unreachable

    try:
        step_init_db(base)
        step_populate(base)
        username, password = step_create_owner(base)

        print("\n      Authenticating...")
        token = _login(base, username, password)

        step_seed_instances(base, token)

    except RuntimeError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    print(f"""
Setup complete!

  API docs:  {public_url}/api/docs
  Username:  {username}

Next steps:
  - Open the Swagger UI above and log in with your credentials
  - Add more users via POST /api/users
  - Set ALLOWED_ORIGINS to your frontend URL in your environment config
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
