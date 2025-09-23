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
- **JWT-protected** endpoints with bcrypt hashed passwords
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

   # JWT configuration
   JWT_SECRET_KEY=super-secret-key
   # JWT_EXPIRE_MINUTES=60
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

5. **Bootstrap data & users**

   *Update the roster (allowed without auth until the first user exists):*

   ```bash
   curl -X POST http://localhost:8000/api/guild/roster/update
   ```

   *Create the first user (role derived from the linked character's guild rank):*

   ```bash
   curl -X POST http://localhost:8000/api/users \
        -H "Content-Type: application/json" \
        -d '{"username":"paella","password":"Paella1.","character_id":123456}'
   ```

   *Obtain a JWT access token:*

   ```bash
   curl -X POST http://localhost:8000/api/auth/token \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d 'username=paella&password=Paella1.'
   ```

   Use the token for subsequent requests:

   ```bash
   curl http://localhost:8000/api/guild/roster \
        -H "Authorization: Bearer <access_token>"
   ```

---

## Endpoints

| Path                               | Method | Auth                    | Description                                                 |
| ---------------------------------- | ------ | ----------------------- | ----------------------------------------------------------- |
| `/api/token`                       | GET    | JWT (all users)         | Get current WoW token price (in gold)                       |
| `/api/guild`                       | GET    | JWT (all users)         | Fetch basic guild info from Blizzard                        |
| `/api/guild/roster`                | GET    | JWT (all users)         | Read cached roster from Postgres                            |
| `/api/guild/roster/update`         | POST   | JWT (owner / admin)     | Fetch roster from Blizzard & upsert into Postgres           |
| `/api/guild/roster/{character_id}` | GET    | JWT (all users)         | Fetch a single character by ID                              |
| `/api/users`                       | POST   | JWT (owner / admin)*    | Create user linked to a guild character (*open until first user) |
| `/api/users`                       | GET    | JWT (owner / admin)     | List all users                                              |
| `/api/auth/token`                  | POST   | Basic (form login)      | Obtain a JWT access token                                   |
| `/api/auth/me`                     | GET    | JWT (all users)         | Inspect the currently authenticated user                    |
| `/api/admin/db/reset`              | POST   | JWT (owner)             | Drop & recreate all tables (dev only)                       |
| `/api/admin/db/populate`           | POST   | JWT (owner)             | Refresh roster, token & guild info; create dev seed user    |
| `/api/events`                      | GET    | JWT (all users)         | List events with optional filters                           |
| `/api/events/{event_id}`           | GET    | JWT (all users)         | Fetch a single event with its sign-ups                      |
| `/api/events`                      | POST   | JWT (owner / admin)     | Create a new event                                          |
| `/api/events/{event_id}`           | PUT    | JWT (owner / admin)     | Update an existing event                                    |
| `/api/events/{event_id}`           | DELETE | JWT (owner / admin)     | Delete an event                                             |
| `/api/events/{event_id}/sign`      | POST   | JWT (all users)         | Sign the authenticated (or delegated) user up for an event  |
| `/api/event/statuses`              | GET    | JWT (all users)         | List allowed sign-up statuses                               |

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
       -H "Authorization: Bearer <owner access token>"
  ```