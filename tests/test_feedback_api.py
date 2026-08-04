"""SIG-025A — Feedback API fixes: atomic persist, endpoint, UI contract."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app, raise_server_exceptions=False)

ITEM_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class _FakeCursor:
    def __init__(self, shared):
        self._shared = shared
        self._last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self._last_sql = " ".join(sql.split())
        self._shared["calls"].append((self._last_sql, params))
        if self._shared.get("fail_on") and self._shared["fail_on"] in self._last_sql:
            raise RuntimeError(self._shared.get("fail_message") or "forced failure")

    def fetchone(self):
        sql = self._last_sql
        if "FROM briefing_items" in sql and "WHERE id" in sql and "UPDATE" not in sql:
            return self._shared.get("item_row")
        if "FROM user_feedback" in sql and "SELECT id" in sql and "INSERT" not in sql:
            return self._shared.get("existing_feedback")
        if "INSERT INTO user_feedback" in sql:
            row = self._shared.get("inserted_row")
            if row is None:
                row = {
                    "id": str(uuid4()),
                    "user_id": USER_ID,
                    "briefing_item_id": ITEM_ID,
                    "category": "funding",
                    "source_name": "inc42",
                    "feedback": "useful",
                    "reason": "great_find",
                    "created_at": datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
                }
                self._shared["inserted_row"] = row
            return row
        return None

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self, shared):
        self._shared = shared

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _FakeCursor(self._shared)

    def commit(self):
        self._shared["commit_count"] += 1

    def rollback(self):
        self._shared["rollback_count"] += 1


def _pool_side_effect(shared):
    def _factory():
        return _FakeConn(shared)

    return _factory


def _base_shared(**overrides):
    shared = {
        "calls": [],
        "commit_count": 0,
        "rollback_count": 0,
        "item_row": {
            "id": ITEM_ID,
            "user_id": USER_ID,
            "category": "funding",
            "source_name": "inc42",
            "feedback": None,
        },
        "existing_feedback": None,
        "inserted_row": None,
        "fail_on": None,
        "fail_message": None,
    }
    shared.update(overrides)
    return shared


def test_feedback_endpoint_exists():
    paths = {route.path for route in app.routes}
    assert "/items/{item_id}/feedback" in paths


def test_feedback_success_one_transaction():
    shared = _base_shared()

    with patch("api.routes.pool.connection", side_effect=_pool_side_effect(shared)):
        response = client.post(
            f"/items/{ITEM_ID}/feedback",
            json={"feedback": "useful", "reason": "great_find"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["feedback"] == "useful"
    assert body["reason"] == "great_find"
    assert body["briefing_item_id"] == ITEM_ID
    assert body["duplicate"] is False

    sqls = [sql for sql, _ in shared["calls"]]
    assert any("INSERT INTO user_feedback" in s for s in sqls)
    assert any("UPDATE briefing_items" in s for s in sqls)
    assert shared["commit_count"] == 1
    assert shared["rollback_count"] == 0


def test_feedback_duplicate_returns_409():
    shared = _base_shared(existing_feedback={"id": str(uuid4())})

    with patch("api.routes.pool.connection", side_effect=_pool_side_effect(shared)):
        response = client.post(
            f"/items/{ITEM_ID}/feedback",
            json={"feedback": "not_relevant"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Already submitted."
    assert shared["commit_count"] == 0
    assert shared["rollback_count"] == 1
    assert not any("INSERT INTO user_feedback" in s for s, _ in shared["calls"])


def test_feedback_rollback_on_update_failure():
    shared = _base_shared(fail_on="UPDATE briefing_items", fail_message="update failed")

    with patch("api.routes.pool.connection", side_effect=_pool_side_effect(shared)):
        response = client.post(
            f"/items/{ITEM_ID}/feedback",
            json={"feedback": "useful", "reason": "already_knew"},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Couldn't save feedback. Please try again."
    assert shared["commit_count"] == 0
    assert shared["rollback_count"] == 1
    assert any("INSERT INTO user_feedback" in s for s, _ in shared["calls"])


def test_feedback_rollback_on_insert_failure():
    shared = _base_shared(fail_on="INSERT INTO user_feedback", fail_message="insert failed")

    with patch("api.routes.pool.connection", side_effect=_pool_side_effect(shared)):
        response = client.post(
            f"/items/{ITEM_ID}/feedback",
            json={"feedback": "useful"},
        )

    assert response.status_code == 500
    assert shared["commit_count"] == 0
    assert shared["rollback_count"] == 1
    assert not any("UPDATE briefing_items" in s for s, _ in shared["calls"])


def test_feedback_invalid_payload():
    response = client.post(
        f"/items/{ITEM_ID}/feedback",
        json={"feedback": "maybe", "reason": "great_find"},
    )
    assert response.status_code == 422


def test_feedback_item_not_found():
    shared = _base_shared(item_row=None)

    with patch("api.routes.pool.connection", side_effect=_pool_side_effect(shared)):
        response = client.post(
            f"/items/{ITEM_ID}/feedback",
            json={"feedback": "useful"},
        )

    assert response.status_code == 404
    assert shared["commit_count"] == 0


def test_frontend_uses_correct_feedback_endpoint():
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    assert "${API_BASE}/items/${encodeURIComponent(item.id)}/feedback" in html
    assert "buildReasonDropdown" in html
    assert "feedback-reason-trigger" in html
    assert "createElement('select')" not in html
    assert "Already knew this" in html
    assert "Wrong funding stage" in html
    assert "Wrong sector" in html
    assert "Too generic" in html
    assert "Very useful" in html
    assert "already_knew" in html
    assert "wrong_stage" in html
    assert "wrong_sector" in html
    assert "too_generic" in html
    assert "great_find" in html
    assert "Feedback submitted successfully." in html
    assert "Already submitted." in html
    assert "Couldn't save feedback. Please try again." in html
    # Do not surface raw API detail strings in the failure path
    assert "body.detail" not in html.split("async function submitItemFeedback")[1].split(
        "async function submitHITL"
    )[0]


def test_feedback_ui_scoped_to_detail_cards():
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    assert "buildFeedbackControls(item)" in html
    # Feedback controls only attached in briefing detail renderer, not HITL list
    hitl_section = html.split("function showHITL(runData)")[1].split(
        "// Utils"
    )[0]
    assert "buildFeedbackControls" not in hitl_section
