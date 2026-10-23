from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.db import DatabaseNotConfiguredError


app = FastAPI(title=get_settings().app_name)


@app.exception_handler(DatabaseNotConfiguredError)
async def database_not_configured_handler(
    _request: Request,
    _exc: DatabaseNotConfiguredError,
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Database is not configured"})


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
