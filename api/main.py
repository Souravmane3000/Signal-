"""FastAPI application entry point for Signal."""

from __future__ import annotations

import logging
import os
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.auth import is_public_path, verify_supabase_jwt
from api.routes import router
from api.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start APScheduler on startup; shut down cleanly on exit."""
    # TEMP DEBUG SIG-024C — process lifecycle (detect --reload / worker death)
    logger.warning(
        "[SIG-024C DEBUG] lifespan START pid=%s ts=%s",
        os.getpid(),
        datetime.now(timezone.utc).isoformat(),
    )
    start_scheduler()
    try:
        yield
    finally:
        logger.warning(
            "[SIG-024C DEBUG] lifespan STOP pid=%s ts=%s",
            os.getpid(),
            datetime.now(timezone.utc).isoformat(),
        )
        stop_scheduler(wait=False)


app = FastAPI(
    title="Signal",
    description="Indian startup intelligence pipeline API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def jwt_auth_middleware(request: Request, call_next):
    """Validate Supabase JWT on every protected route (PRD §20)."""
    path = request.url.path
    if request.method == "OPTIONS" or is_public_path(path):
        return await call_next(request)

    auth_header = request.headers.get("Authorization") or ""
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated"},
        )

    token = auth_header[7:].strip()
    if not token:
        return JSONResponse(
            status_code=401,
            content={"detail": "Not authenticated"},
        )

    try:
        claims = verify_supabase_jwt(token)
    except Exception as exc:
        # HTTPException from verify → preserve status/detail; others → 401.
        from fastapi import HTTPException as FastAPIHTTPException

        if isinstance(exc, FastAPIHTTPException):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or expired token"},
        )

    request.state.user_id = str(claims.get("sub") or "")
    request.state.user_email = claims.get("email")
    request.state.access_token = token
    return await call_next(request)


@app.middleware("http")
async def sig024c_request_lifecycle(request: Request, call_next):
    """TEMP DEBUG SIG-024C — log request enter/exit; do not alter responses."""
    path = request.url.path
    is_resume = "/briefings/" in path and (
        path.endswith("/approve") or path.endswith("/reject")
    )
    if is_resume:
        logger.warning(
            "[SIG-024C DEBUG] HTTP middleware ENTER method=%s path=%s "
            "query=%s pid=%s ts=%s",
            request.method,
            path,
            str(request.url.query),
            os.getpid(),
            datetime.now(timezone.utc).isoformat(),
        )
    try:
        response = await call_next(request)
    except Exception:
        logger.error(
            "[SIG-024C DEBUG] HTTP middleware UNCAUGHT path=%s pid=%s traceback:\n%s",
            path,
            os.getpid(),
            traceback.format_exc(),
        )
        raise
    if is_resume:
        logger.warning(
            "[SIG-024C DEBUG] HTTP middleware EXIT path=%s status=%s pid=%s",
            path,
            getattr(response, "status_code", None),
            os.getpid(),
        )
    return response


# CORS must be outermost so auth middleware JSONResponses still get ACAO headers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://signal-topaz-nu.vercel.app",
        "https://signal-f6n7eoxu8-sourav-manes-projects.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # TEMP DEBUG SIG-024C — capture before generic 500 response (same client body)
    logger.error(
        "[SIG-024C DEBUG] FastAPI unhandled Exception path=%s type=%s "
        "message=%s pid=%s traceback:\n%s",
        request.url.path,
        type(exc).__name__,
        str(exc),
        os.getpid(),
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred."},
    )
