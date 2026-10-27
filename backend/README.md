# MI FINS CRM API

## Local setup

### Run the whole stack with Docker Compose

Each developer needs Docker Desktop (or another Docker Compose compatible runtime) installed once. From the repository root, start the frontend, API, and PostgreSQL together:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open `http://localhost:8443`. The API runs at `http://localhost:8000`. On startup, the API waits for PostgreSQL, applies Alembic migrations, and creates the development demo accounts if they do not already exist. Sign in with `demo.manager` or `demo.staff`; both use `MahiDemo-Only-2026!` locally.

Stop the services with `Ctrl+C`, then run `docker compose down` from the repository root. PostgreSQL data remains in a local named Docker volume. Each developer has a separate database; GitHub contains the setup and migrations, not database data. This Compose configuration is for local development, not production. If port `8443` or `8000` is already occupied, change `FRONTEND_PORT` or `BACKEND_PORT` in the root `.env`.

### Run the frontend and API directly on the host

Use this option if you want to run only PostgreSQL in Docker while running the frontend and API directly on your computer. Compose binds PostgreSQL to localhost only and stores data in a named local volume.

From the repository root, create the local Compose environment file and start PostgreSQL:

```powershell
Copy-Item .env.example .env
docker compose up -d db
```

Then, from this `backend` directory, create and activate the Python virtual environment and install the backend dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

The example files use the same local-only password so the default setup works without editing. If you choose another password, set it in both files before the database's first start; changing the Compose value later does not change the password in an already initialized database. Both `.env` files are ignored by Git; never commit real credentials.

Apply the schema migration and create the first Manager account:

```powershell
alembic upgrade head
python -m app.cli create-manager
```

For local UI testing, the development-only demo command creates one Manager and one Staff account:

```powershell
python -m app.cli create-demo-accounts
```

Both use the local-only password `MahiDemo-Only-2026!`, which the development login picker fills for convenience. Never use this password outside local development. The command refuses to run when `APP_ENV=production` and will not overwrite accounts if either demo User ID or email already exists. Demo accounts require the configured database and current migrations, just like normal accounts.

The Manager can then create and deactivate Staff accounts through the authenticated `/users` API. Each account has a unique User ID, email, and password. Account creation accepts a password that the Manager must share with the new Staff member through a separate secure channel.

After a teammate pulls changes, they can start the same local database with `docker compose up -d db` from the repository root, then run `alembic upgrade head` from this backend directory to apply any new schema migrations. Each computer has its own database volume and its own data. `npm install` and `pip install` install application packages; they do not install or start a database service. Starting Docker explicitly keeps dependency installation from silently starting background services.

Run the API and tests from this directory:

```powershell
python -m uvicorn app.main:app --reload
pytest
```

The local development environment uses HTTP-only, SameSite=Lax cookies without the `Secure` flag so cookies work over local HTTP. Set `APP_ENV=production` behind HTTPS to enable `Secure` cookies.

## Authentication API

- `POST /auth/login` — sign in with User ID and password; returns the profile and CSRF token and sets an HTTP-only session cookie.
- `GET /auth/me` — return the current profile and CSRF token.
- `POST /auth/logout` — revoke the current session. Send the returned CSRF token in the `X-CSRF-Token` header.
- `GET /users` — Manager-only staff directory.
- `POST /users` — Manager-only Staff account creation. Send the CSRF token in the `X-CSRF-Token` header.
- `PATCH /users/{id}/status` — Manager-only Staff activation/deactivation. Deactivation revokes that Staff member's sessions.

## Customer and enquiry APIs (Phase 3)

All staff dashboard endpoints require an authenticated session. Mutating dashboard requests also require the `X-CSRF-Token` returned by `/auth/login` or `/auth/me`.

- `GET /customers?limit=50&offset=0` — list active customer records; merged source records remain stored but are hidden from this directory.
- `GET /enquiries?status=New&service_type=Real%20Estate&source=Phone&search=...&limit=50&offset=0` — paginated enquiry list with optional filters.
- `POST /enquiries` — create an enquiry with either a new `customer` object (`name`, `phone`, optional `email`) or an existing `customer_id`, plus `service_type` and `source`.
- `PATCH /enquiries/{id}/status` — update status within the allowed lifecycle and optionally record an outcome reason or do-not-contact instruction for Lost enquiries.
- `PATCH /enquiries/{id}/handler` — any authenticated staff member can set or clear the informational handler; the selected user must be an active Staff account and this does not restrict enquiry access.
- `POST /customers/{target_id}/link` — explicitly link a source customer record to a target. Its enquiries move to the target; the source record is retained with a link to the target.
- `POST /public/enquiries` — public website intake. Accepts `customer` contact details and `service_type`; source is set to `Website`, status starts as `New`, and the response does not reveal customer data.

## Follow-up API (Phase 4)

- `POST /enquiries/{id}/follow-ups` records a completed follow-up date/time. Omit `completed_at` to use the current UTC time, or supply an ISO datetime with a timezone.
- `GET /enquiries/{id}/follow-ups` returns that enquiry's paginated completed history.
- `PUT /enquiries/{id}/follow-up` sets or clears `next_follow_up_at` with an ISO datetime including its timezone (or `null` to clear it).
- `GET /follow-ups?bucket=due-today|upcoming|overdue&limit=50&offset=0` returns paginated actionable enquiries. “Due today” uses `BUSINESS_TIMEZONE`, which defaults to `Asia/Kolkata`.

These routes require a staff session; writes also require the CSRF header. Completed follow-up counts are included on enquiry responses. Recording a completed contact clears its current scheduled reminder; staff can then schedule the next contact. Finalized enquiries also lose scheduled dates, while completed history is retained. Follow-ups cannot be scheduled or recorded after a final outcome or a do-not-contact instruction.

Website intake creates a separate customer record without trying to infer identity from name, email, or phone. Staff can explicitly link that record to an existing customer after review. The initial public intake throttle is in-memory and per application process; production deployments with multiple workers should add a shared rate-limit store or edge rate limiting.

The client-facing roles are `manager` and `staff`. A Manager provisions Staff accounts; there is no public registration endpoint. Developer database access and schema changes are not exposed through the client API.

Login currently verifies User ID and password, then issues the session. Credential verification is separate from session creation so a future email OTP step can be inserted between them. Email OTP delivery and verification are not part of this phase.

## Run the dashboard with the API

Start the API from this `backend` directory after configuring the development database, applying migrations, and creating the Manager account:

```powershell
python -m uvicorn app.main:app --reload
```

In a second terminal, from the repository root, start the Vite dashboard:

```powershell
npm.cmd run dev
```

The Vite development server proxies `/auth` and `/users` to `http://127.0.0.1:8000`, so the browser uses the same origin for cookie sessions and does not need a token in browser storage. Set `VITE_BACKEND_URL` in the environment if the API is listening elsewhere. The current production frontend also expects the API to be available on the same origin; deployment routing will be configured in the deployment phase.

Sign in with the Manager User ID and password created by `python -m app.cli create-manager`. The Manager can add Staff accounts from **Settings → Staff accounts**. Email OTP is planned but is not active yet.
