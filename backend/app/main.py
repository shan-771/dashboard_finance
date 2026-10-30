import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.crm import router as crm_router
from app.api.health import router as health_router
from app.api.notifications import router as notifications_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.db import DatabaseNotConfiguredError
from app.db import get_session_factory
from app.retention import purge_expired_deleted_enquiries


logger = logging.getLogger(__name__)
RETENTION_SWEEP_INTERVAL_SECONDS = 60


async def deletion_retention_sweeper() -> None:
    while True:
        try:
            session_factory = get_session_factory()
            purged = await asyncio.to_thread(purge_expired_deleted_enquiries, session_factory)
            if purged:
                logger.info("Permanently purged %s expired deleted enquiries", purged)
        except Exception:
            logger.exception("Could not purge expired deleted enquiries")
        await asyncio.sleep(RETENTION_SWEEP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(application: FastAPI):
    sweeper = None
    if getattr(application.state, "enable_retention_sweeper", True) and get_settings().database_url:
        sweeper = asyncio.create_task(deletion_retention_sweeper())
    try:
        yield
    finally:
        if sweeper is not None:
            sweeper.cancel()
            with suppress(asyncio.CancelledError):
                await sweeper


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)


@app.exception_handler(DatabaseNotConfiguredError)
async def database_not_configured_handler(
    _request: Request,
    _exc: DatabaseNotConfiguredError,
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Database is not configured"})


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(crm_router)
app.include_router(notifications_router)
