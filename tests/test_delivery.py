"""SIG-020A — Gmail Delivery node unit tests (SMTP mocked)."""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

from agent.nodes.delivery import (
    _MAX_ATTEMPTS,
    _RETRY_BACKOFF_SECONDS,
    _build_message,
    delivery,
)
from agent.state import ErrorCode


def _state(**overrides):
    base = {
        "run_id": "run_delivery_001",
        "briefing_final": "## Signal Weekly Briefing\n\nTest body.",
        "user_config": {"delivery_email": "recipient@example.com"},
    }
    base.update(overrides)
    return base


def test_retry_policy_locked():
    assert _RETRY_BACKOFF_SECONDS == (30, 60, 120)
    assert _MAX_ATTEMPTS == 4


def test_subject_includes_signal_weekly_briefing():
    msg = _build_message(
        sender="sender@gmail.com",
        recipient="to@example.com",
        body="body",
    )
    assert msg["Subject"].startswith("Signal Weekly Briefing - ")


def test_delivery_success_returns_sent():
    from email import message_from_string

    mock_smtp = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_smtp
    mock_cm.__exit__.return_value = False

    with patch.dict(
        "os.environ",
        {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "app-pass"},
    ):
        with patch("agent.nodes.delivery.smtplib.SMTP_SSL", return_value=mock_cm):
            result = delivery(_state())

    assert result == {"delivery_status": "sent"}
    mock_smtp.login.assert_called_once_with("sender@gmail.com", "app-pass")
    mock_smtp.sendmail.assert_called_once()
    args = mock_smtp.sendmail.call_args[0]
    assert args[0] == "sender@gmail.com"
    assert args[1] == ["recipient@example.com"]
    parsed = message_from_string(args[2])
    assert "Signal Weekly Briefing - " in parsed["Subject"]
    payload = parsed.get_payload(decode=True).decode("utf-8")
    assert "Test body" in payload


def test_delivery_uses_briefing_final_no_llm():
    from email import message_from_string
    import agent.nodes.delivery as delivery_mod

    mock_smtp = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_smtp
    mock_cm.__exit__.return_value = False
    body = "UNIQUE_BRIEFING_CONTENT_XYZ"

    with patch.dict(
        "os.environ",
        {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "app-pass"},
    ):
        with patch("agent.nodes.delivery.smtplib.SMTP_SSL", return_value=mock_cm):
            result = delivery(_state(briefing_final=body))

    assert result["delivery_status"] == "sent"
    parsed = message_from_string(mock_smtp.sendmail.call_args[0][2])
    payload = parsed.get_payload(decode=True).decode("utf-8")
    assert body in payload
    assert not hasattr(delivery_mod, "OpenAI")
    src = open(delivery_mod.__file__, encoding="utf-8").read()
    assert "openai" not in src.lower()
    assert "chat.completions" not in src


def test_missing_delivery_email_returns_failed():
    with patch.dict(
        "os.environ",
        {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "app-pass"},
    ):
        result = delivery(_state(user_config={}))

    assert result["delivery_status"] == "failed"
    assert result["error"]["code"] == ErrorCode.DELIVERY_FAILED


def test_retries_then_returns_failed_without_raising():
    mock_smtp = MagicMock()
    mock_smtp.login.side_effect = smtplib.SMTPException("smtp down")
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_smtp
    mock_cm.__exit__.return_value = False

    with patch.dict(
        "os.environ",
        {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "app-pass"},
    ):
        with patch("agent.nodes.delivery.smtplib.SMTP_SSL", return_value=mock_cm):
            with patch("agent.nodes.delivery.time.sleep") as mock_sleep:
                result = delivery(_state())

    assert result["delivery_status"] == "failed"
    assert result["error"]["code"] == ErrorCode.DELIVERY_FAILED
    assert mock_smtp.login.call_count == _MAX_ATTEMPTS
    assert mock_sleep.call_args_list == [
        ((30,),),
        ((60,),),
        ((120,),),
    ]


def test_auth_failure_sets_gmail_auth_failed_code():
    mock_smtp = MagicMock()
    mock_smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad creds")
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_smtp
    mock_cm.__exit__.return_value = False

    with patch.dict(
        "os.environ",
        {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "wrong"},
    ):
        with patch("agent.nodes.delivery.smtplib.SMTP_SSL", return_value=mock_cm):
            with patch("agent.nodes.delivery.time.sleep"):
                result = delivery(_state())

    assert result["delivery_status"] == "failed"
    assert result["error"]["code"] == ErrorCode.GMAIL_AUTH_FAILED


def test_missing_gmail_env_raises():
    with patch.dict("os.environ", {"GMAIL_ADDRESS": "", "GMAIL_APP_PASSWORD": ""}, clear=False):
        # Clear specifically for this call via patch on getenv path inside _require
        with patch("agent.nodes.delivery.os.getenv", return_value=""):
            try:
                delivery(_state())
                raised = False
            except RuntimeError as exc:
                raised = True
                assert "GMAIL_ADDRESS" in str(exc) or "GMAIL_APP_PASSWORD" in str(exc)
    assert raised


def test_connection_refused_propagates():
    mock_cm = MagicMock()
    mock_cm.__enter__.side_effect = ConnectionRefusedError("port blocked")

    with patch.dict(
        "os.environ",
        {"GMAIL_ADDRESS": "sender@gmail.com", "GMAIL_APP_PASSWORD": "app-pass"},
    ):
        with patch("agent.nodes.delivery.smtplib.SMTP_SSL", return_value=mock_cm):
            try:
                delivery(_state())
                raised = False
            except ConnectionRefusedError:
                raised = True
    assert raised


if __name__ == "__main__":
    test_retry_policy_locked()
    test_subject_includes_signal_weekly_briefing()
    test_delivery_success_returns_sent()
    test_delivery_uses_briefing_final_no_llm()
    test_missing_delivery_email_returns_failed()
    test_retries_then_returns_failed_without_raising()
    test_auth_failure_sets_gmail_auth_failed_code()
    test_missing_gmail_env_raises()
    test_connection_refused_propagates()
    print("Delivery tests passed.")
