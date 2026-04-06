# WoW Guild API — CLAUDE.md

## What this project is

A FastAPI + PostgreSQL backend for managing a World of Warcraft guild. It exposes a REST API consumed by a frontend (not in this repo). Key features:

- Guild roster fetched from the Blizzard Game Data API and cached in Postgres
- WoW token price endpoint
- Raid/instance browser (all expansions + current season bosses)
- Guild event scheduling with sign-ups
- JWT authentication tied to guild rank (owner / administrator / user)
- Self-update mechanism via `git pull` triggered from an admin endpoint

## Tech stack

- **Python 3.14**, FastAPI, SQLModel, SQLAlchemy, psycopg3 (`psycopg[binary]`)
- **PostgreSQL** — primary data store (no YAML serving in production)
- **Alembic** — migrations
- **SQLAdmin** — admin panel at `/admin`
- **slowapi** — rate limiting
- `bcrypt`, `python-jose` — password hashing and JWT

## Project layout

```
main.py                  # All FastAPI routes
lib/
  auth.py                # Blizzard OAuth token (DB-backed, upsert on conflict)
  blizzard_journal.py    # Raid fetching from Blizzard journal API (used by seed endpoint)
  cache.py               # TTL in-memory cache decorator
  db.py                  # SQLModel models + engine + init_db()
  events.py              # Event/sign-up helpers
  guild.py               # Guild info + roster from Blizzard API
  instances.py           # DB-only instance reads + seed helpers
  schemas.py             # Pydantic response schemas
  security.py            # JWT, role checks, ensure_authenticated_or_bootstrap
  updater.py             # GitHub release check + git pull + restart
  wow.py                 # WoW token price, classes/races index
scripts/
  generate_instances_yaml.py   # Standalone CLI — fetches raids from Blizzard and writes YAML
  import_instances.py          # Standalone CLI — seeds DB from YAML archive files
data/instances/          # YAML archive written by seed endpoint (debug/backup only)
alembic/                 # Migrations
tests/                   # pytest test suite
start_dev.sh             # Dev startup (autodetects fish/bash)
```

## Database models (`lib/db.py`)

| Model | Description |
|---|---|
| `GuildMember` | Guild roster, PK = Blizzard character_id |
| `User` | App users linked to a GuildMember, role = owner/administrator/user |
| `OAuthToken` | Single-row Blizzard OAuth token cache (id=1) |
| `Event` | Guild events with start/end time |
| `EventSignUp` | Per-user sign-up for events (Assist/Late/Tentative/Absence) |
| `Expansion` | WoW expansion (e.g. "The War Within") |
| `Instance` | Raid instance, FK to Expansion |
| `Encounter` | Boss encounter, FK to Instance |

DB URL is built from `POSTGRES_*` env vars; falls back to SQLite for tests.
Uses `postgresql+psycopg://` (psycopg3 driver).

## Auth and roles

- Role is derived automatically from guild rank at user creation: rank 0 → owner, rank 1 → administrator, else → user
- `security.ensure_authenticated_or_bootstrap()` allows unauthenticated access when no users exist (bootstrap state)
- `security.require_roles("owner", "administrator")` used as a FastAPI dependency for protected endpoints

## API endpoints summary

| Tag | Endpoint | Auth |
|---|---|---|
| Auth | `POST /auth/token` | none |
| Auth | `GET /auth/me` | authenticated |
| WoW | `GET /token` | bootstrap-or-auth |
| Guild | `GET /guild` | bootstrap-or-auth |
| Guild | `GET /guild/roster` | bootstrap-or-auth |
| Guild | `POST /guild/roster/update` | owner/administrator |
| Guild | `GET /guild/roster/{id}` | bootstrap-or-auth |
| Users | `POST /users` | owner/administrator |
| Users | `GET /users` | owner/administrator |
| Instances | `GET /instances` | bootstrap-or-auth |
| Instances | `GET /instances/{blizzard_id}` | bootstrap-or-auth |
| Events | `GET /events/{id}` | bootstrap-or-auth |
| Events | `POST /events` | owner/administrator |
| Events | sign-up endpoints | authenticated |
| Admin | `POST /admin/db/init` | none (bootstrap) |
| Admin | `POST /admin/db/reset` | owner |
| Admin | `POST /admin/db/populate` | owner/administrator |
| Admin | `POST /admin/db/seed-dev-user` | owner/administrator |
| Admin | `POST /admin/instances/seed` | owner/administrator |
| Admin | `GET /admin/updates/check` | owner/administrator |
| Admin | `POST /admin/updates/apply` | owner |

Swagger UI: `http://localhost:8000/api/docs`

## Instance data flow

Instance data is **always served from PostgreSQL**. YAML files under `data/instances/` are a debug/backup archive only.

1. `POST /admin/instances/seed` — fetches raids from Blizzard journal API, writes YAML archive, seeds DB
2. On startup, if the instance table is empty, auto-seeds from YAML archive (`seed_from_yaml`)
3. `scripts/generate_instances_yaml.py` — standalone CLI for regenerating the YAML archive manually
4. `scripts/import_instances.py` — standalone CLI for seeding DB from YAML archive

### Current season raid IDs (update each season)

Defined in **two places** — keep in sync:
- `lib/blizzard_journal.py`: `CURRENT_SEASON_RAID_IDS`
- `scripts/generate_instances_yaml.py`: `CURRENT_SEASON_RAID_IDS`

Current values (TWW Season 2 — Liberation of Undermine):
```python
CURRENT_SEASON_RAID_IDS: set[int] = {1307, 1314, 1308}
CURRENT_KEYSTONE_SEASON_ID = 17
```

## Environment variables (`.env.example`)

| Variable | Description |
|---|---|
| `CLIENT_ID` / `CLIENT_SECRET` | Blizzard API credentials |
| `REGION` | API region: `eu`, `us`, `kr`, `tw` |
| `LOCALE` | API locale: `en_US`, `es_ES`, etc. |
| `GUILD_NAME` / `GUILD_SLUG` | Guild identifier |
| `POSTGRES_USER/PASSWORD/DB/HOST/PORT` | DB connection |
| `DATABASE_URL` | Optional override for full DB URL |
| `JWT_SECRET_KEY` | Long random secret for JWT signing |
| `JWT_EXPIRE_MINUTES` | Optional, default 60 |
| `GITHUB_REPO` | Override if forked (default: `GFerreiroS/wow-guild-api`) |

## Bootstrap procedure

The server runs `alembic upgrade head` automatically on startup (via `Procfile` / Dockerfile CMD), so tables are always created/migrated before the app starts.

Run the setup script to configure and bootstrap in one go:
```sh
python setup.py
```

The script:
1. Asks for Blizzard credentials (shows dev portal URL), guild info, DB config
2. Generates a JWT secret automatically
3. Writes `.env`
4. Waits for the server to come up
5. Calls `POST /api/admin/db/init`, populates roster, creates owner user, seeds instances

For a server that's already running (Heroku/Dokku/remote):
```sh
python setup.py --url https://your-api-url.com
```
If `.env` already exists, configuration is skipped. Use `--reconfigure` to redo it.

For local dev only: `POST /api/admin/db/seed-dev-user` creates user `paella` / `Paella1.` linked to character Lapaella.

## Alembic workflow

`alembic upgrade head` runs automatically on every deploy (Procfile/Dockerfile). `POST /admin/updates/apply` also runs it after `git pull`.

When you change a model in `lib/db.py`:
```sh
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

All migrations are idempotent — safe to run against a DB that was previously created with `create_all()`.

## Running locally

```sh
# bash/zsh
source .venv/bin/activate

# fish
source .venv/bin/activate.fish

# or just use the script (autodetects shell)
./start_dev.sh
```

Uvicorn runs at `http://localhost:8000`.

## Running tests

```sh
pytest
```

Tests use SQLite (no Postgres needed). The `conftest.py` sets up an in-memory DB per test.

## Python 3.14 compatibility notes

- All model files must have `from __future__ import annotations` (PEP 649 lazy annotations — SQLModel requires it)
- Use `psycopg[binary]` (psycopg3), not `psycopg2-binary` (no 3.14 wheel)
- Loosen version pins on compiled packages (`pydantic`, `pydantic_core`, `greenlet`, `bcrypt`, etc.) so pip can find newer PyO3-compatible wheels

## Commit style

Multiple small focused commits, no signature lines.
