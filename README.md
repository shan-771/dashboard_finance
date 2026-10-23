# MI FINS CRM Dashboard

## Start the full development stack

Install Docker Desktop once, then from the repository root run:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open the dashboard at <http://localhost:8443>. The API is available at <http://localhost:8000>. Compose starts PostgreSQL, waits for it to become ready, applies database migrations, creates the local demo accounts, and starts the frontend and API.

Sign in with either account:

| Role | User ID | Password |
| --- | --- | --- |
| Manager | `demo.manager` | `MahiDemo-Only-2026!` |
| Staff | `demo.staff` | `MahiDemo-Only-2026!` |

These shared credentials are for local development only. Do not use them outside development.

Press `Ctrl+C` to stop the foreground logs, then run `docker compose down` to stop the containers. The local database remains in a Docker volume between runs. Each developer has their own database and data; Git tracks the Compose setup and Alembic migrations, not database files.

If ports `8443`, `8000`, or `5432` are already in use, change `FRONTEND_PORT`, `BACKEND_PORT`, or `POSTGRES_PORT` in the root `.env`. For host-based Python setup and API details, see [backend/README.md](backend/README.md).
