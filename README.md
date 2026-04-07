# WoW Guild API

A **FastAPI + PostgreSQL** backend for managing a World of Warcraft guild. Exposes a REST API for a frontend to consume.

**Features:**
- Guild roster fetched from Blizzard's Game Data API and cached in Postgres
- WoW token price
- Raid/instance browser (all expansions + current season)
- Guild event scheduling with per-user sign-ups
- JWT authentication with role-based access (owner / administrator / user)
- Self-update via `git pull` triggered from an admin endpoint

---

## Quickstart

### Requirements

- Python 3.14+
- Docker + Docker Compose (recommended), or a PostgreSQL instance
- A [Blizzard developer account](https://develop.battle.net/access/clients) with a client application

### Setup

```bash
git clone https://github.com/GFerreiroS/wow-guild-api.git
cd wow-guild-api
python setup.py
```

The setup script will:
1. Ask for your Blizzard API credentials (provides the link to the dev portal)
2. Ask for your guild name, region, and other config
3. Generate a secure JWT secret automatically
4. Write `.env`
5. Wait for the server to be ready
6. Bootstrap the database and create your owner account

Then start the server:
```bash
docker compose up -d
```

The setup script will detect the server and finish the bootstrap automatically.

---

## Hosting

### Docker Compose (self-hosted)

```bash
python setup.py          # configure + bootstrap
docker compose up -d     # start server
```

### Heroku

```bash
heroku config:set CLIENT_ID=xxx CLIENT_SECRET=xxx REGION=eu LOCALE=en_US \
  GUILD_NAME="My Guild" GUILD_SLUG=my-guild \
  POSTGRES_USER=... POSTGRES_PASSWORD=... POSTGRES_DB=... POSTGRES_HOST=... POSTGRES_PORT=5432 \
  JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))") \
  ALLOWED_ORIGINS=https://myguild.com

git push heroku main

python setup.py --url https://my-app.herokuapp.com
```

### Dokku

```bash
dokku config:set APP CLIENT_ID=xxx CLIENT_SECRET=xxx ...   # same vars as above
git push dokku main
python setup.py --url https://my-app.mydomain.com
```

> For Heroku/Dokku, `alembic upgrade head` runs automatically via the `Procfile` on every deploy.

---

## Configuration

All configuration is via environment variables. Copy `.env.example` to `.env` or use the setup script.

| Variable | Required | Description |
|---|---|---|
| `CLIENT_ID` | Yes | Blizzard API client ID |
| `CLIENT_SECRET` | Yes | Blizzard API client secret |
| `REGION` | Yes | API region: `eu`, `us`, `kr`, `tw` |
| `LOCALE` | Yes | API locale: `en_GB`, `en_US`, `ko_KR`, `zh_TW` |
| `GUILD_NAME` | Yes | Guild display name |
| `GUILD_SLUG` | Yes | Guild URL slug |
| `POSTGRES_USER` | Yes | Database user |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `POSTGRES_DB` | Yes | Database name |
| `POSTGRES_HOST` | Yes | Database host |
| `POSTGRES_PORT` | Yes | Database port (usually `5432`) |
| `JWT_SECRET_KEY` | Yes | Secret for signing JWTs (min 32 chars) |
| `JWT_EXPIRE_MINUTES` | No | Token lifetime in minutes (default: 60) |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins (default: `*`) |
| `GITHUB_REPO` | No | Override if you fork (default: `GFerreiroS/wow-guild-api`) |

---

## API Endpoints

| Tag | Method | Path | Auth | Description |
|---|---|---|---|---|
| Auth | POST | `/api/auth/token` | — | Obtain a JWT |
| Auth | GET | `/api/auth/me` | authenticated | Current user profile |
| WoW | GET | `/api/token` | bootstrap-or-auth | WoW token price |
| Guild | GET | `/api/guild` | bootstrap-or-auth | Guild info from Blizzard |
| Guild | GET | `/api/guild/roster` | bootstrap-or-auth | Cached roster |
| Guild | POST | `/api/guild/roster/update` | owner/admin | Refresh roster from Blizzard |
| Guild | GET | `/api/guild/roster/{id}` | bootstrap-or-auth | Single character |
| Users | POST | `/api/users` | owner/admin | Create user linked to a character |
| Users | GET | `/api/users` | owner/admin | List all users |
| Instances | GET | `/api/instances` | bootstrap-or-auth | List raids (filter by expansion, type, season) |
| Instances | GET | `/api/instances/{id}` | bootstrap-or-auth | Raid detail with boss encounters |
| Events | POST | `/api/events` | owner/admin | Create an event |
| Events | GET | `/api/events/{id}` | bootstrap-or-auth | Event detail with sign-ups |
| Events | POST | `/api/events/{id}/signups` | authenticated | Sign up for an event |
| Admin | POST | `/api/admin/db/init` | — | Create tables (safe to re-run) |
| Admin | POST | `/api/admin/db/reset` | owner | Drop & recreate all tables |
| Admin | POST | `/api/admin/db/populate` | owner/admin | Fetch guild + roster from Blizzard |
| Admin | POST | `/api/admin/instances/seed` | owner/admin | Fetch raids from Blizzard + seed DB |
| Admin | GET | `/api/admin/updates/check` | owner/admin | Check for a new release on GitHub |
| Admin | POST | `/api/admin/updates/apply` | owner | Pull latest release and restart |

> **bootstrap-or-auth**: endpoint is open when no users exist (first-run), requires auth after that.

Swagger UI: `http://localhost:8000/api/docs`

---

## Roles

Roles are assigned explicitly when creating a user. The first user created is always `owner` regardless of the role requested.

| Role | Can do |
|---|---|
| `owner` | Everything, including DB reset and applying updates |
| `administrator` | Roster updates, user creation, instance seeding, update checks |
| `user` | Read-only access to roster, instances, events; can sign up for events |

---

## Development

```bash
# Create and activate virtualenv
python3.14 -m venv .venv
source .venv/bin/activate        # bash/zsh
source .venv/bin/activate.fish   # fish

pip install -r requirements.txt

# Start the dev server (autodetects fish/bash)
./start_dev.sh
```

Swagger UI at `http://localhost:8000/api/docs`.

### Running tests

```bash
pytest
```

Tests use SQLite — no Postgres needed.

### Database migrations

When you change a model in `lib/db.py`:

```bash
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

`alembic upgrade head` runs automatically on every deploy (via `Procfile` and Dockerfile).

### Instance data

Raid data is fetched from the Blizzard Journal API and stored in Postgres. To reseed:

```bash
# Via API (requires owner/admin JWT)
POST /api/admin/instances/seed
```

YAML files under `data/instances/` are written as a debug archive only — Postgres is always the source of truth.

---

## License

MIT
