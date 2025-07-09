# Wow Guild API

A **FastAPI** service that wraps Blizzard’s OAuth2 + World of Warcraft APIs to expose:

- **WoW Token price** (`/api/token`)
- **Guild info** (`/api/guild`)
- **Guild roster** (cached in Postgres via `/api/guild/roster` and `/api/guild/roster/update`)
- **User-character linking** (signup, list users)
- **Admin utilities** (reset & populate schema)

---

## Features

- **OAuth2 Client Credentials** for Blizzard API  
- **SQLModel + Alembic** migrations on PostgreSQL  
- **Docker & Docker Compose** for quick local setup  
- **Rate-limited**, **thread-pooled** background scripts for static data  
- **API key**-protected admin endpoints  
- **Password rules**: min 8 chars, upper+lower, digit, special char  

---

## Quickstart

1. **Clone & enter**  
   ```bash
   git clone https://github.com/GFerreiroS/wow-guild-api.git
   cd wow-guild-api
   ```

2. **Copy & edit** your `.env` (see `.env.example`):

   ```ini
   # Blizzard OAuth2
   CLIENT_ID=…
   CLIENT_SECRET=…
   REGION=eu
   LOCALE=en_US

   # Your guild
   GUILD_NAME=…
   GUILD_SLUG=…

   # Postgres
   POSTGRES_USER=fastapi
   POSTGRES_PASSWORD=changeme
   POSTGRES_DB=wowdb
   POSTGRES_HOST=localhost
   POSTGRES_PORT=5432

   # Admin API key
   ADMIN_API_KEY=test
   ```

3. **Bring up** with Docker Compose

   ```bash
   docker-compose up --build
   ```

   * Postgres runs on `localhost:5432`
   * FastAPI app on `http://localhost:8000/api`

4. **Run migrations** (inside the FastAPI container or your venv):

   ```bash
   alembic upgrade head
   ```

5. **Populate roster & dev user**:

   ```bash
   curl -X POST http://localhost:8000/api/admin/db/populate \
        -H "X-API-Key: test"
   ```

---

## Endpoints

| Path                               | Method | Auth    | Description                                         |
| ---------------------------------- | ------ | ------- | --------------------------------------------------- |
| `/api/token`                       | GET    | none    | Get current WoW token price (in gold)               |
| `/api/guild`                       | GET    | none    | Fetch basic guild info from Blizzard                |
| `/api/guild/roster`                | GET    | none    | Read cached roster from Postgres                    |
| `/api/guild/roster/update`         | POST   | API key | Fetch roster from Blizzard & upsert into Postgres   |
| `/api/guild/roster/{character_id}` | GET    | none    | Fetch a single character by ID                      |
| `/api/users`                       | POST   | none    | Create user linked to a guild character             |
| `/api/users`                       | GET    | API key | List all users                                      |
| `/api/admin/db/reset`              | POST   | API key | Drop & recreate all tables (dev only)               |
| `/api/admin/db/populate`           | POST   | API key | Refresh roster, token & guild info; create dev user |

See the **Swagger UI** at `http://localhost:8000/docs`.

---

## Development

* **Virtualenv**:

  ```bash
  python3.13 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

* **Run**

  ```bash
  uvicorn main:app --reload
  ```

* **Migrations** with Alembic:

  ```bash
  alembic revision --autogenerate -m "…"
  alembic upgrade head
  ```

* **Rebuild DB** (drops all data):

  ```bash
  curl -X POST http://localhost:8000/api/admin/db/reset \
       -H "X-API-Key: <your admin key>"
  ```