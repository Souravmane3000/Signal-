"""Gmail Delivery node — smtplib + App Password (SIG-020A).

Runs on Approve/Edit path only (graph edges enforce DEC-004).
Episodic memory is already written before this node executes.
"""

from __future__ import annotations

import smtplib
import time
from datetime import datetime
from email.mime.text import MIMEText

from dotenv import load_dotenv
import os

from agent.state import ErrorCode, SignalState

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 465
# PRD Section 10 / TASKS SIG-020A — 3 retries with these backoffs between attempts.
_RETRY_BACKOFF_SECONDS = (30, 60, 120)
_MAX_ATTEMPTS = 1 + len(_RETRY_BACKOFF_SECONDS)


def _require_gmail_env() -> tuple[str, str]:
    load_dotenv()
    address = (os.getenv("GMAIL_ADDRESS") or "").strip()
    password = (os.getenv("GMAIL_APP_PASSWORD") or "").strip()
    if not address or not password:
        raise RuntimeError(
            "GMAIL_ADDRESS or GMAIL_APP_PASSWORD missing from .env. "
            "SIG-020A stop condition (H-005)."
        )
    return address, password


def _recipient_email(state: SignalState) -> str:
    user_config = state.get("user_config") or {}
    email = (user_config.get("delivery_email") or "").strip()
    if not email:
        raise ValueError(
            "user_config.delivery_email is missing or empty — "
            "cannot deliver briefing."
        )
    return email


def _build_message(
    *,
    sender: str,
    recipient: str,
    body: str,
) -> MIMEText:
    subject = f"Signal Weekly Briefing - {datetime.now().strftime('%b %d, %Y')}"
    msg = MIMEText(body or "", _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    return msg


def _send_once(sender: str, password: str, recipient: str, msg: MIMEText) -> None:
    with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, timeout=30) as server:
        server.login(sender, password)
        server.sendmail(sender, [recipient], msg.as_string())


def _is_auth_failure(exc: BaseException) -> bool:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return True
    message = str(exc).lower()
    return "authentication" in message or "username and password" in message


def delivery(state: SignalState) -> dict:
    """Email briefing_final via Gmail SMTP. Never regenerates content."""
    sender, password = _require_gmail_env()

    try:
        recipient = _recipient_email(state)
    except ValueError as exc:
        print(f"Delivery failed: {exc}")
        return {
            "delivery_status": "failed",
            "error": {
                "code": ErrorCode.DELIVERY_FAILED,
                "node": "delivery",
                "message": str(exc),
                "recoverable": True,
            },
        }

    body = state.get("briefing_final") or ""
    msg = _build_message(sender=sender, recipient=recipient, body=body)

    last_exc: BaseException | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            _send_once(sender, password, recipient, msg)
            print(f"Delivery sent to {recipient} for run {state.get('run_id', '')}")
            return {"delivery_status": "sent"}
        except ConnectionRefusedError:
            # Port blocked — SIG-020A stop condition; do not mask as soft failure.
            raise
        except Exception as exc:
            last_exc = exc
            print(
                f"Delivery attempt {attempt + 1}/{_MAX_ATTEMPTS} failed: {exc}"
            )
            if attempt < len(_RETRY_BACKOFF_SECONDS):
                time.sleep(_RETRY_BACKOFF_SECONDS[attempt])

    assert last_exc is not None
    code = (
        ErrorCode.GMAIL_AUTH_FAILED
        if _is_auth_failure(last_exc)
        else ErrorCode.DELIVERY_FAILED
    )
    # Do NOT raise — episodic memory already persisted (DEC-004 / PRD Section 10).
    print(f"Delivery failed after {_MAX_ATTEMPTS} attempts: {last_exc}")
    return {
        "delivery_status": "failed",
        "error": {
            "code": code,
            "node": "delivery",
            "message": str(last_exc),
            "recoverable": True,
        },
    }
