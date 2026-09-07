"""Supabase Auth helpers and FastAPI JWT dependency for Signal."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx
import jwt
from fastapi import HTTPException, Request
from jwt import InvalidTokenError

logger = logging.getLogger(__name__)

PUBLIC_PATH_EXACT = frozenset(
    {
        "/health",
        "/auth/login",
        "/auth/signup",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/favicon.ico",
    }
)


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    email: Optional[str] = None


def _supabase_url() -> str:
    url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    if not url:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL is not configured",
        )
    return url


def _supabase_anon_key() -> str:
    key = os.getenv("SUPABASE_ANON_KEY") or ""
    if not key:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_ANON_KEY is not configured",
        )
    return key


def jwt_secret() -> str:
    """Return the Supabase JWT secret (HS256 legacy). Empty when unset."""
    return os.getenv("SUPABASE_JWT_SECRET") or ""


_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _jwks_client_for(jwks_url: str) -> jwt.PyJWKClient:
    """Reuse one PyJWKClient per JWKS URL so key fetches are cached in-process."""
    client = _jwks_clients.get(jwks_url)
    if client is None:
        client = jwt.PyJWKClient(jwks_url)
        _jwks_clients[jwks_url] = client
    return client


def is_public_path(path: str) -> bool:
    if path in PUBLIC_PATH_EXACT:
        return True
    if path.startswith("/docs") or path.startswith("/redoc"):
        return True
    return False


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """Validate a Supabase access token (ES256 JWKS or legacy HS256 secret)."""
    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        ) from exc

    alg = str(header.get("alg") or "")
    try:
        if alg in ("ES256", "RS256"):
            # Current Supabase signing keys are asymmetric (JWKS).
            jwks_url = f"{_supabase_url()}/auth/v1/.well-known/jwks.json"
            signing_key = _jwks_client_for(jwks_url).get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
            )
        elif alg == "HS256":
            secret = jwt_secret()
            if not secret:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "SUPABASE_JWT_SECRET is not configured. "
                        "Protected routes cannot authenticate HS256 tokens."
                    ),
                )
            claims = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
                options={"require": ["exp", "sub"]},
            )
        else:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token",
            )
    except HTTPException:
        raise
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        ) from exc
    except Exception as exc:
        # JWKS network / key lookup failures
        logger.exception("JWT verification failed")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        ) from exc

    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return claims


def get_current_user(request: Request) -> AuthUser:
    """Read the authenticated user attached by JWT middleware."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    email = getattr(request.state, "user_email", None)
    return AuthUser(user_id=str(user_id), email=str(email) if email else None)


def _auth_headers() -> dict[str, str]:
    key = _supabase_anon_key()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _normalize_auth_error(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        msg = payload.get("msg") or payload.get("error_description") or payload.get(
            "error"
        )
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
        err = payload.get("error")
        if isinstance(err, dict):
            nested = err.get("message") or err.get("msg")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return fallback


def signup_with_password(email: str, password: str) -> dict[str, Any]:
    """Create a user via Supabase Auth email/password signup."""
    url = f"{_supabase_url()}/auth/v1/signup"
    try:
        response = httpx.post(
            url,
            headers=_auth_headers(),
            json={"email": email, "password": password},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        logger.exception("Supabase signup network error")
        raise HTTPException(
            status_code=503,
            detail="Auth service unavailable. Please try again.",
        ) from exc

    payload: Any
    try:
        payload = response.json()
    except Exception:
        payload = {}

    if response.status_code >= 400:
        raise HTTPException(
            status_code=400,
            detail=_normalize_auth_error(payload, "Signup failed"),
        )

    return _extract_session(payload, email=email)


def login_with_password(email: str, password: str) -> dict[str, Any]:
    """Sign in via Supabase Auth password grant."""
    url = f"{_supabase_url()}/auth/v1/token?grant_type=password"
    try:
        response = httpx.post(
            url,
            headers=_auth_headers(),
            json={"email": email, "password": password},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        logger.exception("Supabase login network error")
        raise HTTPException(
            status_code=503,
            detail="Auth service unavailable. Please try again.",
        ) from exc

    payload: Any
    try:
        payload = response.json()
    except Exception:
        payload = {}

    if response.status_code >= 400:
        # Map invalid credentials to a clear 401 without leaking internals.
        detail = _normalize_auth_error(payload, "Invalid email or password")
        status = 401
        lowered = detail.lower()
        if "invalid" in lowered or "credentials" in lowered or "password" in lowered:
            detail = "Invalid email or password"
        raise HTTPException(status_code=status, detail=detail)

    return _extract_session(payload, email=email)


def _extract_session(payload: dict[str, Any], *, email: str) -> dict[str, Any]:
    """Normalize Supabase signup/login payloads into a session dict."""
    access_token = payload.get("access_token")
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}

    # Some signup responses nest the session under "session".
    if not access_token and isinstance(payload.get("session"), dict):
        session = payload["session"]
        access_token = session.get("access_token")
        if not user and isinstance(session.get("user"), dict):
            user = session["user"]

    if not access_token:
        raise HTTPException(
            status_code=400,
            detail=(
                "Signup succeeded but no session token was returned. "
                "Confirm email confirmation is disabled for this project, "
                "or complete email verification before logging in."
            ),
        )

    user_id = str(user.get("id") or "").strip()
    user_email = str(user.get("email") or email).strip()
    if not user_id:
        # Decode unverified claims only to recover sub when user object is thin.
        try:
            claims = jwt.decode(
                access_token,
                options={"verify_signature": False},
                algorithms=["HS256"],
            )
            user_id = str(claims.get("sub") or "").strip()
            user_email = str(claims.get("email") or user_email).strip()
        except Exception:
            user_id = ""

    if not user_id:
        raise HTTPException(
            status_code=500,
            detail="Auth response missing user id",
        )

    return {
        "access_token": str(access_token),
        "token_type": str(payload.get("token_type") or "bearer"),
        "expires_in": payload.get("expires_in"),
        "user_id": user_id,
        "email": user_email,
    }
