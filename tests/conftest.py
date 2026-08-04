"""Disable APScheduler during API/unit test collection (SIG-023-deploy).

Also provides JWT helpers for Slice 5-Auth — secret must be set before
`api.main` is imported by test modules.
"""

from __future__ import annotations

import os
import time
from typing import Optional
from uuid import uuid4

# Must run before api.main lifespan / TestClient imports start the scheduler.
os.environ.setdefault("SIGNAL_SCHEDULER_ENABLED", "0")

# Fail-closed JWT middleware requires a secret; use a deterministic test value.
TEST_JWT_SECRET = "test-supabase-jwt-secret"
TEST_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
TEST_USER_EMAIL = "tester@signal.test"

os.environ.setdefault("SUPABASE_JWT_SECRET", TEST_JWT_SECRET)
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")


def mint_access_token(
    *,
    sub: str = TEST_USER_ID,
    email: str = TEST_USER_EMAIL,
    secret: Optional[str] = None,
    exp_delta: int = 3600,
    audience: str = "authenticated",
) -> str:
    """Mint an HS256 JWT shaped like a Supabase access token."""
    import jwt

    now = int(time.time())
    payload = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "aud": audience,
        "iat": now,
        "exp": now + exp_delta,
    }
    return jwt.encode(payload, secret or TEST_JWT_SECRET, algorithm="HS256")


def auth_headers(
    *,
    user_id: str = TEST_USER_ID,
    email: str = TEST_USER_EMAIL,
    token: Optional[str] = None,
) -> dict[str, str]:
    access = token if token is not None else mint_access_token(sub=user_id, email=email)
    return {"Authorization": f"Bearer {access}"}


def attach_default_auth(client, *, user_id: str = TEST_USER_ID) -> None:
    """Auto-attach a valid Bearer token to protected TestClient requests.

    Public routes (/health, /auth/*) are left untouched so auth tests can assert 401.
    Explicit Authorization headers on a call always win.
    """
    if getattr(client, "_signal_default_auth", False):
        return

    original_request = client.request

    def _request(method, url, **kwargs):
        path = str(url)
        headers = dict(kwargs.pop("headers", None) or {})
        public = (
            path == "/health"
            or path.startswith("/auth/")
            or path.startswith("/docs")
            or path.startswith("/openapi")
        )
        if not public and "Authorization" not in headers:
            headers.update(auth_headers(user_id=user_id))
        return original_request(method, url, headers=headers, **kwargs)

    client.request = _request  # type: ignore[method-assign]
    client._signal_default_auth = True  # type: ignore[attr-defined]


def other_user_id() -> str:
    return str(uuid4())
