"""FastAPI application: middleware, static/template wiring, and route registration
for SmartReco (ARCHITECTURE.md \u00a712).
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from smartreco_agent.src.auth.dependencies import get_current_user
from smartreco_agent.src.core.exceptions.exceptions import (
    AppException,
    AppExceptionCode,
)
from smartreco_agent.src.db.pool import close_pool, open_pool
from smartreco_agent.src.routes.admin import router as admin_router
from smartreco_agent.src.routes.auth import router as auth_router
from smartreco_agent.src.routes.cron import router as cron_router
from smartreco_agent.src.routes.events import router as events_router
from smartreco_agent.src.routes.health import router as health_router
from smartreco_agent.src.routes.web import router as web_router
from smartreco_agent.src.settings import settings
from smartreco_agent.src.web.templating import STATIC_DIR
from smartreco_agent.utils.pylogger import get_python_logger

logger = get_python_logger(settings.PYTHON_LOG_LEVEL)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured request/response logging, skipped for static assets to avoid noise."""

    async def dispatch(self, request: Request, call_next: Callable):
        if not settings.REQUEST_LOGGING_ENABLED or request.url.path.startswith("/static"):
            return await call_next(request)

        start_time = time.time()
        response = await call_next(request)
        duration_ms = (time.time() - start_time) * 1000

        logger.info(
            "request_handled",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response


class CurrentUserMiddleware(BaseHTTPMiddleware):
    """Populates `request.state.user` from the signed session cookie.

    Cheap and synchronous - no DB round trip - so it costs nothing on the
    hot ingest path or on anonymous page views (ARCHITECTURE.md \u00a713)."""

    async def dispatch(self, request: Request, call_next: Callable):
        request.state.user = get_current_user(request)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("SmartReco server starting up")
    await open_pool()
    yield
    await close_pool()
    logger.info("SmartReco server shutting down")


app = FastAPI(title="SmartReco", lifespan=lifespan)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CurrentUserMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(web_router)
app.include_router(events_router)
app.include_router(admin_router)
app.include_router(cron_router)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(
        f"Unhandled exception for {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=AppExceptionCode.INTERNAL_SERVER_ERROR.response_code,
        content={
            "detail_message": str(exc),
            "message": AppExceptionCode.INTERNAL_SERVER_ERROR.message,
            "error_code": AppExceptionCode.INTERNAL_SERVER_ERROR.error_code,
        },
    )


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    logger.warning(
        f"App exception for {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=exc.response_code,
        content={
            "detail_message": exc.detail_message,
            "message": exc.message,
            "error_code": exc.error_code,
        },
    )
