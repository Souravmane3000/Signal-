"""Slice 5-Auth — signup/login/JWT middleware/RLS scoping tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from api.main import app
from tests.conftest import (
    TEST_USER_EMAIL,
    TEST_USER_ID,
    auth_headers,
    mint_access_token,
    other_user_id,
)

client = TestClient(app, raise_server_exceptions=False)
FRONTEND = Path("frontend/index.html")
SCHEMA = Path("database/schema.sql")


def test_signup_success():
    session = {
        "access_token": mint_access_token(),
        "token_type": "bearer",
        "expires_in": 3600,
        "user_id": TEST_USER_ID,
        "email": "new@signal.test",
    }
    with (
        patch("api.routes.signup_with_password", return_value=session),
        patch("api.routes._user_needs_onboarding", return_value=True),
    ):
        response = client.post(
            "/auth/signup",
            json={"email": "new@signal.test", "password": "secret12"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["id"] == TEST_USER_ID
    assert body["user"]["email"] == "new@signal.test"
    assert body["needs_onboarding"] is True


def test_login_success():
    session = {
        "access_token": mint_access_token(),
        "token_type": "bearer",
        "expires_in": 3600,
        "user_id": TEST_USER_ID,
        "email": TEST_USER_EMAIL,
    }
    with (
        patch("api.routes.login_with_password", return_value=session),
        patch("api.routes._user_needs_onboarding", return_value=False),
    ):
        response = client.post(
            "/auth/login",
            json={"email": TEST_USER_EMAIL, "password": "secret12"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["needs_onboarding"] is False
    assert body["user"]["email"] == TEST_USER_EMAIL


def test_login_invalid_password():
    from fastapi import HTTPException

    with patch(
        "api.routes.login_with_password",
        side_effect=HTTPException(status_code=401, detail="Invalid email or password"),
    ):
        response = client.post(
            "/auth/login",
            json={"email": TEST_USER_EMAIL, "password": "wrong-password"},
        )

    assert response.status_code == 401
    assert "Invalid" in response.json()["detail"]


def test_signup_invalid_email():
    response = client.post(
        "/auth/signup",
        json={"email": "not-an-email", "password": "secret12"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid email"


def test_protected_endpoint_without_jwt_returns_401():
    response = client.get("/briefings")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_protected_endpoint_with_valid_jwt():
    with patch("api.routes.pool.connection") as mock_conn:
        conn = MagicMock()
        cur = MagicMock()
        mock_conn.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cur
        cur.fetchall.return_value = []

        response = client.get("/briefings", headers=auth_headers())

    assert response.status_code == 200
    assert response.json()["briefings"] == []


def test_jwt_rejected_after_logout_clears_token():
    """Frontend clears in-memory JWT; subsequent API calls without Bearer → 401."""
    # Valid request first
    with patch("api.routes.pool.connection") as mock_conn:
        conn = MagicMock()
        cur = MagicMock()
        mock_conn.return_value.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = cur
        cur.fetchall.return_value = []
        ok = client.get("/config", headers=auth_headers())
    assert ok.status_code == 200

    # After logout the client sends no Authorization header
    denied = client.get("/config")
    assert denied.status_code == 401


def test_invalid_jwt_signature_rejected():
    bad = mint_access_token(secret="wrong-secret-value")
    response = client.get(
        "/briefings",
        headers={"Authorization": f"Bearer {bad}"},
    )
    assert response.status_code == 401


def test_expired_jwt_rejected():
    expired = mint_access_token(exp_delta=-10)
    response = client.get(
        "/briefings",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert response.status_code == 401


def test_run_uses_jwt_user_id_not_body():
    spoof = str(uuid4())
    with patch("api.routes.execute_pipeline") as mock_exec:
        from api.schemas import RunResponse, RuntimeMetrics

        mock_exec.return_value = RunResponse(
            run_id="r1",
            thread_id="t1",
            status="completed",
            briefing_summary="",
            delivery_status=None,
            runtime_metrics=RuntimeMetrics(),
            error=None,
        )
        response = client.post(
            "/run",
            headers=auth_headers(),
            json={"user_id": spoof, "run_type": "manual"},
        )

    assert response.status_code == 200
    req = mock_exec.call_args[0][0]
    assert req.user_id == TEST_USER_ID
    assert req.user_id != spoof


def test_briefings_query_scoped_to_jwt_user():
    captured = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            captured["sql"] = " ".join(sql.split())
            captured["params"] = params

        def fetchall(self):
            return []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            return FakeCursor()

    with patch("api.routes.pool.connection", return_value=FakeConn()):
        response = client.get("/briefings", headers=auth_headers())

    assert response.status_code == 200
    assert "WHERE br.user_id = %s" in captured["sql"]
    assert captured["params"][0] == TEST_USER_ID


def test_metrics_query_scoped_to_jwt_user():
    captured = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            captured["sql"] = " ".join(sql.split())
            captured["params"] = params

        def fetchall(self):
            return []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            return FakeCursor()

    with patch("api.routes.pool.connection", return_value=FakeConn()):
        response = client.get("/metrics/runs", headers=auth_headers())

    assert response.status_code == 200
    assert "WHERE m.user_id = %s" in captured["sql"]
    assert captured["params"][0] == TEST_USER_ID


def test_feedback_rejects_other_users_item():
    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            self._sql = " ".join(sql.split())
            self._params = params

        def fetchone(self):
            # No row when user_id doesn't match — cross-user blocked
            return None

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            return FakeCursor()

        def commit(self):
            pass

        def rollback(self):
            pass

    item_id = str(uuid4())
    with patch("api.routes.pool.connection", return_value=FakeConn()):
        response = client.post(
            f"/items/{item_id}/feedback",
            headers=auth_headers(),
            json={"feedback": "useful"},
        )

    assert response.status_code == 404


def test_memory_namespace_uses_jwt_user():
    store = MagicMock()
    store.get.return_value = None
    with patch("api.routes._get_store", return_value=store):
        response = client.get("/memory/semantic", headers=auth_headers())

    assert response.status_code == 200
    ns = store.get.call_args[0][0]
    assert ns == ("user", TEST_USER_ID, "semantic")


def test_cross_user_briefing_not_visible():
    """User A cannot load User B's briefing_runs row."""
    other = other_user_id()
    run_id = str(uuid4())

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, params=None):
            self.sql = " ".join(sql.split())
            self.params = params

        def fetchone(self):
            # Simulate RLS/app filter: no row for non-owner
            if self.params and str(TEST_USER_ID) in [str(p) for p in self.params]:
                return None
            return {
                "id": run_id,
                "user_id": other,
                "thread_id": "t",
                "status": "completed",
                "run_at": None,
                "final_briefing": "secret",
                "graph_version": "1.0",
            }

        def fetchall(self):
            return []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def cursor(self):
            return FakeCursor()

    with patch("api.routes.pool.connection", return_value=FakeConn()):
        response = client.get(f"/briefings/{run_id}", headers=auth_headers())

    assert response.status_code == 404


def test_rls_policies_present_in_schema():
    sql = SCHEMA.read_text(encoding="utf-8")
    required = [
        ("user_configs", "user_configs_user_scope"),
        ("briefing_runs", "briefing_runs_user_scope"),
        ("briefing_items", "briefing_items_user_scope"),
        ("agent_run_metrics", "agent_run_metrics_user_scope"),
        ("user_feedback", "user_feedback_user_scope"),
        ("agent_memory", "agent_memory_user_scope"),
        ("funding_rounds", "funding_rounds_user_scope"),
        ("companies", "companies_authenticated_read"),
    ]
    for table, policy in required:
        assert f"ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"CREATE POLICY {policy}" in sql
        if table not in ("companies", "funding_rounds"):
            assert "auth.uid() = user_id" in sql


def test_frontend_auth_contract():
    html = FRONTEND.read_text(encoding="utf-8")
    assert "auth-screen" in html or 'id="view-auth"' in html or "id=\"auth-" in html
    assert "/auth/login" in html
    assert "/auth/signup" in html
    assert "Authorization" in html
    assert "Bearer" in html
    # JWT must not be persisted
    assert "localStorage.setItem" not in html or "access_token" not in html.split(
        "localStorage"
    )[0]
    # Stronger: no token storage APIs used for JWT
    assert "localStorage.setItem(" not in html
    assert "sessionStorage.setItem(" not in html
    assert "document.cookie" not in html
    assert "password" in html.lower()
    assert "logout" in html.lower()
    assert "onboarding" in html.lower()
