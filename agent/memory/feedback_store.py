"""user_feedback persistence helpers (SIG-022).

Used by Feedback Collector and (later) SIG-023 Procedural Memory Updater.
Does not update procedural/semantic/episodic memory.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

ALLOWED_FEEDBACK = frozenset({"useful", "not_relevant"})
ALLOWED_REASONS = frozenset(
    {
        "already_knew",
        "wrong_stage",
        "wrong_sector",
        "too_generic",
        "great_find",
    }
)

_FALLBACK_AUTH_EMAIL = "signal-builder@local.test"


def _get_pool():
    """Reuse the ConnectionPool from SIG-P2-002 — do not open a second connection."""
    from agent.graph import _pool

    if _pool is None:
        raise RuntimeError(
            "Postgres ConnectionPool unavailable (SIG-P2-002 not complete)."
        )
    return _pool


def _resolve_user_uuid(conn, user_id: str) -> uuid.UUID:
    raw = (user_id or "").strip()
    if raw:
        try:
            return uuid.UUID(raw)
        except ValueError:
            pass
    row = conn.execute(
        "SELECT id FROM auth.users WHERE email = %s LIMIT 1",
        (_FALLBACK_AUTH_EMAIL,),
    ).fetchone()
    if row:
        raw_id = row["id"] if isinstance(row, dict) else row[0]
        if raw_id:
            return raw_id if isinstance(raw_id, uuid.UUID) else uuid.UUID(str(raw_id))
    raise RuntimeError(
        "user_id must be an auth.users UUID for user_feedback "
        f"(SIG-022). Got {raw!r}; no fallback user {_FALLBACK_AUTH_EMAIL!r}."
    )


def _row_to_dict(row: Any) -> dict:
    if isinstance(row, dict):
        return dict(row)
    return {k: row[k] for k in row.keys()}


def insert_feedback(
    *,
    user_id: str,
    feedback: str,
    briefing_item_id: Optional[str] = None,
    category: Optional[str] = None,
    source_name: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict:
    """INSERT one row into user_feedback. Returns the inserted row as a dict.

    Does not swallow DB errors.
    """
    if feedback not in ALLOWED_FEEDBACK:
        raise ValueError(
            f"feedback must be one of {sorted(ALLOWED_FEEDBACK)}, got {feedback!r}"
        )
    if reason is not None and reason not in ALLOWED_REASONS:
        raise ValueError(
            f"reason must be one of {sorted(ALLOWED_REASONS)} or None, got {reason!r}"
        )

    item_uuid = None
    if briefing_item_id is not None and str(briefing_item_id).strip():
        item_uuid = str(uuid.UUID(str(briefing_item_id)))

    pool = _get_pool()
    with pool.connection() as conn:
        uid = _resolve_user_uuid(conn, user_id)
        row = conn.execute(
            """
            INSERT INTO user_feedback (
                user_id, briefing_item_id, category, source_name, feedback, reason
            ) VALUES (
                %s, %s, %s, %s, %s, %s
            )
            RETURNING
                id, user_id, briefing_item_id, category, source_name,
                feedback, reason, created_at
            """,
            (
                str(uid),
                item_uuid,
                category,
                source_name,
                feedback,
                reason,
            ),
        ).fetchone()
        conn.commit()
    return _row_to_dict(row)


def fetch_all_feedback_for_user(user_id: str) -> list[dict]:
    """Return all user_feedback rows for user_id as a list of dicts."""
    pool = _get_pool()
    with pool.connection() as conn:
        uid = _resolve_user_uuid(conn, user_id)
        rows = conn.execute(
            """
            SELECT
                id, user_id, briefing_item_id, category, source_name,
                feedback, reason, created_at
            FROM user_feedback
            WHERE user_id = %s
            ORDER BY created_at ASC
            """,
            (str(uid),),
        ).fetchall()
    result = [_row_to_dict(r) for r in rows]
    if not isinstance(result, list):
        raise RuntimeError("fetch_all_feedback_for_user must return a list")
    return result
