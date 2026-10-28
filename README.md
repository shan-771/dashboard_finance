# MI FINS CRM Dashboard

MI FINS is a real estate and finance CRM. The repository currently contains a Vite/React dashboard and a FastAPI backend backed by PostgreSQL.

## Current implementation status

| Area | Status | Details |
| --- | --- | --- |
| Backend foundation | Implemented | FastAPI app, environment settings, PostgreSQL connection, Alembic migrations, health endpoints |
| Authentication and staff roles | Implemented | Manager and Staff accounts, password hashing, cookie sessions, CSRF protection, Manager-only staff administration |
| Customers and enquiries | Implemented and tested | Unified enquiry records, website intake, lifecycle validation, first-claim-wins staff handling, filtering, pagination, explicit customer linking |
| Follow-ups | Implemented: Phase 4 | Completed follow-up history, per-enquiry notes, next scheduled dates, and upcoming/overdue/due-today views |
| Edit/deletion approvals | Implemented: Phase 5 | Staff requests, Manager decisions, stale-request protection, audit history, and confirmed soft deletion |
| Dashboard CRM integration and reporting | Implemented: Phase 7 | Customer directory and independent Closed/Open/Lost enquiry views, CRM outcome summaries, source/service breakdowns, enquiry listing, follow-up actions, calendar view, and connection status are connected to CRM APIs |
| Property management | Deferred for a later phase | Start after dashboard CRM integration and reporting; listing fields, removal behavior, and photo storage still need to be agreed |

The dashboard creates and lists enquiries, displays customers with each of their independent enquiries, separates Closed/Open/Lost outcomes, shows CRM outcome/source/service summaries, and provides a follow-up calendar. Staff explicitly pick new enquiries; the first claim assigns the enquiry. After the call, the handler saves short notes and a next follow-up date defaulting to two days from now; only then does it appear in the Follow-ups section. Competing claims receive a conflict message, and the API limits each Staff account to 10 claim attempts per minute using database-stored counters without polling. The Follow-ups tiles are ordered Upcoming, Overdue, then Due today. The connection indicator calls the database health endpoint and displays the backend's configured business timezone. The current dashboard queries load at most 100 customers and 100 enquiries; the directory and summaries therefore cover those returned records. Property management is the next planned phase and its listing fields, removal behavior, and photo storage need to be finalized first. Use the API documentation at `http://localhost:8000/docs` to explore or call the backend directly. The development login and demo accounts remain available for testing.

## Start the full development stack

Install Docker Desktop, then run these commands from the repository root:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open the dashboard at <http://localhost:8443>. The API runs at <http://localhost:8000>; interactive API documentation is at <http://localhost:8000/docs>. Compose starts PostgreSQL, applies migrations, seeds local demo accounts, and starts the API and dashboard.

### Local demo accounts

| Role | User ID | Password |
| --- | --- | --- |
| Manager | `demo.manager` | `MahiDemo-Only-2026!` |
| Staff | `demo.staff` | `MahiDemo-Only-2026!` |

These shared credentials are for local development only. The demo-account command refuses to run when `APP_ENV=production`. Do not use these credentials outside local development.

Stop the services with `Ctrl+C`, then run `docker compose down`. The PostgreSQL data remains in a local Docker volume. Each developer has their own database; Git tracks the setup and migrations, not database files. If ports `8443`, `8000`, or `5432` are occupied, set `FRONTEND_PORT`, `BACKEND_PORT`, or `POSTGRES_PORT` in the root `.env`.

## Backend setup without Docker Compose

For host-based backend development, Python 3.11 and PostgreSQL are required. Start only the database with `docker compose up -d db`, then follow the virtual environment, migration, and account setup instructions in [backend/README.md](backend/README.md).

Run the backend tests from the `backend` directory:

```powershell
pytest
```

Latest recorded result: **21 passed**.

## Implemented CRM API

Dashboard endpoints require a signed-in staff session. Mutating dashboard requests require the `X-CSRF-Token` returned by `/auth/login` or `/auth/me`.

| Method and path | Purpose |
| --- | --- |
| `GET /customers` | Paginated active customer list; linked source records are retained and hidden |
| `GET /enquiries` | Paginated enquiry list; filters include status, service type, source, handler, and customer search |
| `POST /enquiries` | Create a manual enquiry using a new or existing customer |
| `PATCH /enquiries/{id}/status` | Change status through the allowed lifecycle and record outcome or do-not-contact details |
| `POST /enquiries/{id}/claim` | Staff first-claim an unassigned enquiry; competing claims receive `409` with the current handler |
| `PUT /enquiries/{id}/contact` | The handler saves short call notes and schedules a next follow-up; this moves `Assigned` to `Follow-ups` |
| `PATCH /enquiries/{id}/handler` | Manager-only handler changes; Staff must use the atomic claim endpoint |
| `POST /customers/{target_id}/link` | Explicitly link two customer records and move the source customer's enquiries to the target |
| `POST /public/enquiries` | Public website intake; creates a `New` enquiry with source `Website` and returns no customer details |

One customer can have multiple independent enquiries. Service type and source are stored per enquiry. The backend does not infer that two matching names or phone numbers identify the same person; staff can link customer records explicitly after review.

The initial service types are `Real Estate` and `Finance/Loans`. Sources include `Website`, `Phone`, `Referral`, and `Walk-in`, with other source values allowed. Current enquiry statuses are `New`, `Assigned`, `Attended` (legacy), `Follow-ups`, `Closed`, `Open`, and `Lost`. Follow-up counts are not required before choosing a final outcome; a do-not-contact request is recorded on a Lost enquiry and cannot be cleared through the status API. A Staff account can make up to 10 claim attempts per minute; the counter is stored in PostgreSQL.

The initial public intake rate limiter is in memory and per API process. Production deployments with multiple workers need a shared or edge rate limiter. Email OTP is not implemented. The distinction between Administrator and Manager privileges remains undecided; current account-management endpoints are Manager-only.

Phase 5 adds `POST /enquiries/{id}/change-requests` for Staff edit or deletion requests, Manager review at `GET /change-requests` and `PATCH /change-requests/{id}`, and a separate `POST /change-requests/{id}/confirm-deletion` step for approved deletions. Enquiry edit proposals currently cover `service_type` and `source`; shared customer contact fields are not edited from an enquiry request. Approved deletion is a soft deletion that retains the enquiry, follow-up history, request, and decision audit. Manager direct edits use `PATCH /enquiries/{id}` and are audited. Requests are rejected as stale if the enquiry changed after submission or before deletion confirmation.

Follow-ups are recorded per enquiry. `POST /enquiries/{id}/follow-ups` records the completed contact and closes the enquiry, clearing its current reminder; `GET /enquiries/{id}/follow-ups` lists completed history; `PUT /enquiries/{id}/follow-up` sets or clears a timezone-aware next date; and `GET /follow-ups?bucket=due-today|upcoming|overdue` returns actionable enquiries. “Due today” uses the configured `BUSINESS_TIMEZONE` (default `Asia/Kolkata`). Final outcomes clear scheduled dates, and do-not-contact enquiries cannot be scheduled or logged for further contact; completed history remains available.

## Authentication and configuration

- `POST /auth/login` issues an HTTP-only, SameSite=Lax session cookie and CSRF token.
- `GET /auth/me` returns the signed-in profile and CSRF token.
- `POST /auth/logout` revokes the session; send the CSRF token in `X-CSRF-Token`.
- Managers create and deactivate Staff accounts through `/users`; deactivation revokes existing sessions.
- Database URL, session lifetime, environment, and cookie settings are configured with environment variables. See [backend/.env.example](backend/.env.example).
- Local development cookies use HTTP. Set `APP_ENV=production` behind HTTPS to enable the Secure cookie flag.

For backend API details and host-based setup, see [backend/README.md](backend/README.md).
