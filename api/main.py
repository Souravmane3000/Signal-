"""FastAPI application entry point for Signal."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

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
    start_scheduler()
    try:
        yield
    finally:
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
        claims = await asyncio.to_thread(verify_supabase_jwt, token)
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
    logger.exception("Unhandled exception on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred."},
    )
