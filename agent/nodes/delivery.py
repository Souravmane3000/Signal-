"""Gmail Delivery node — smtplib + App Password (SIG-020A).

Runs on Approve/Edit path only (graph edges enforce DEC-004).
Episodic memory is already written before this node executes.
"""

from __future__ import annotations

import html
import logging
import re
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv
import os

from agent.state import ErrorCode, SignalState

logger = logging.getLogger(__name__)

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 465
# PRD Section 10 / TASKS SIG-020A — 3 retries with these backoffs between attempts.
_RETRY_BACKOFF_SECONDS = (30, 60, 120)
_MAX_ATTEMPTS = 1 + len(_RETRY_BACKOFF_SECONDS)

_SECTION_KEYS = (
    "executive summary",
    "funding highlights",
    "ecosystem moves",
    "trends to watch",
)


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


def _strip_md_inline(text: str) -> str:
    value = text or ""
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value)
    value = re.sub(r"__(.*?)__", r"\1", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", value)
    return value.strip()


def _split_briefing_sections(markdown: str) -> dict[str, str]:
    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    sections: dict[str, list[str]] = {"_preamble": []}
    current = "_preamble"
    title = "Signal Weekly Briefing"
    for line in lines:
        h3 = re.match(r"^###\s+(.+?)\s*$", line)
        h2 = re.match(r"^##\s+(.+?)\s*$", line)
        if h3:
            current = h3.group(1).strip().lower()
            sections.setdefault(current, [])
            continue
        if h2:
            title = h2.group(1).strip() or title
            continue
        sections.setdefault(current, []).append(line)
    out = {key: "\n".join(value).strip() for key, value in sections.items()}
    out["_title"] = title
    return out


def _body_to_paragraphs(body: str) -> list[str]:
    chunks = re.split(r"\n\s*\n", body or "")
    return [re.sub(r"\n", " ", c).strip() for c in chunks if c.strip()]


def _body_to_bullets(body: str) -> list[str]:
    bullets: list[str] = []
    for line in (body or "").split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^[-*•]\s+(.+)$", line) or re.match(r"^\d+\.\s+(.+)$", line)
        bullets.append(_strip_md_inline(m.group(1) if m else line))
    return [b for b in bullets if b]


def _render_briefing_html(
    body: str,
    *,
    graph_version: str = "",
    generated_at: datetime | None = None,
) -> str:
    """Presentation-only HTML for the weekly briefing email."""
    when = generated_at or datetime.now()
    date_label = when.strftime("%b %d, %Y")
    version = (graph_version or os.getenv("GRAPH_VERSION") or "1.0").strip()
    sections = _split_briefing_sections(body)
    structured = any(sections.get(key) for key in _SECTION_KEYS)
    title = html.escape(sections.get("_title") or "Signal Weekly Briefing")

    def _p_block(text: str) -> str:
        paras = _body_to_paragraphs(text)
        if not paras:
            return (
                '<p style="margin:0;font-size:15px;line-height:1.7;'
                'color:#475569;">No content.</p>'
            )
        return "".join(
            f'<p style="margin:0 0 12px;font-size:15px;line-height:1.7;'
            f'color:#334155;">{html.escape(_strip_md_inline(p))}</p>'
            for p in paras
        )

    def _parse_funding_bullet(bullet: str) -> dict[str, str]:
        company = bullet
        amount = ""
        stage = ""
        money = re.search(r"\$[\d.,]+\s*[MBKmbk]?", bullet)
        if money:
            amount = re.sub(r"\s+", "", money.group(0)).upper()
        stage_m = re.search(
            r"\b(pre[-\s]?seed|seed|series\s*[a-d]|series_[a-d]|grant|accelerator)\b",
            bullet,
            re.I,
        )
        if stage_m:
            stage = stage_m.group(1).replace("_", " ")
        parts = re.split(r"\s+[—\-–:]\s+", bullet, maxsplit=1)
        if len(parts) > 1:
            company = parts[0]
        else:
            raise_m = re.search(
                r"\braises?\b|\braised\b|\bcloses?\b|\bclosed\b",
                bullet,
                re.I,
            )
            if raise_m and raise_m.start() > 0:
                company = bullet[: raise_m.start()].strip()
        return {
            "company": company[:120],
            "amount": amount,
            "stage": stage,
            "summary": bullet,
        }

    def _funding_cards(text: str) -> str:
        bullets = _body_to_bullets(text)
        if not bullets:
            return (
                '<p style="margin:0;font-size:14px;color:#64748b;">'
                "No funding highlights this week.</p>"
            )
        cards = []
        for bullet in bullets:
            card = _parse_funding_bullet(bullet)
            stage_html = (
                f'<span style="font-size:11px;font-weight:600;letter-spacing:0.06em;'
                f'text-transform:uppercase;color:#64748b;margin-right:10px;">'
                f'{html.escape(card["stage"])}</span>'
                if card["stage"]
                else ""
            )
            amount_html = (
                f'<p style="margin:0 0 8px;font-size:17px;font-weight:700;'
                f'color:#0284c7;">{html.escape(card["amount"])}</p>'
                if card["amount"]
                else ""
            )
            cards.append(
                '<table role="presentation" width="100%" cellpadding="0" '
                'cellspacing="0" style="margin:0 0 14px;border:1px solid #e2e8f0;'
                'border-radius:10px;background:#f8fafc;">'
                '<tr><td style="padding:14px 16px;">'
                f'<p style="margin:0 0 6px;font-size:16px;font-weight:700;'
                f'color:#0f172a;letter-spacing:-0.01em;">'
                f'{html.escape(card["company"])}</p>'
                f"{amount_html}"
                f'<p style="margin:0 0 8px;">{stage_html}</p>'
                f'<p style="margin:0;font-size:14px;line-height:1.55;color:#475569;">'
                f'{html.escape(card["summary"])}</p>'
                "</td></tr></table>"
            )
        return "".join(cards)

    def _bullet_list(text: str) -> str:
        bullets = _body_to_bullets(text)
        if not bullets:
            return (
                '<p style="margin:0;font-size:14px;color:#64748b;">'
                "No items this week.</p>"
            )
        items = "".join(
            '<tr><td style="padding:10px 0;border-bottom:1px solid #f1f5f9;'
            'font-size:14px;line-height:1.55;color:#334155;">'
            f"• {html.escape(b)}</td></tr>"
            for b in bullets
        )
        return (
            f'<table role="presentation" width="100%" cellpadding="0" '
            f'cellspacing="0">{items}</table>'
        )

    def _trend_cards(text: str) -> str:
        bullets = _body_to_bullets(text)
        if not bullets:
            return (
                '<p style="margin:0;font-size:14px;color:#64748b;">'
                "No trends highlighted this week.</p>"
            )
        return "".join(
            '<table role="presentation" width="100%" cellpadding="0" '
            'cellspacing="0" style="margin:0 0 10px;">'
            '<tr><td style="border-left:3px solid #0ea5e9;padding:8px 0 8px 12px;'
            f'font-size:14px;line-height:1.6;color:#334155;">{html.escape(b)}'
            "</td></tr></table>"
            for b in bullets
        )

    if structured:
        body_html = (
            f'<h1 style="margin:0 0 20px;font-size:24px;line-height:1.25;'
            f'font-weight:700;color:#0f172a;letter-spacing:-0.02em;">{title}</h1>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="margin:0 0 16px;border:1px solid #e2e8f0;border-radius:12px;'
            'background:#ffffff;">'
            '<tr><td style="padding:18px 20px;">'
            '<h2 style="margin:0 0 12px;font-size:18px;color:#0f172a;'
            'letter-spacing:-0.02em;">Executive Summary</h2>'
            f"{_p_block(sections.get('executive summary', ''))}"
            "</td></tr></table>"
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="margin:0 0 16px;border:1px solid #e2e8f0;border-radius:12px;'
            'background:#ffffff;">'
            '<tr><td style="padding:18px 20px;">'
            '<h2 style="margin:0 0 12px;font-size:18px;color:#0f172a;'
            'letter-spacing:-0.02em;">Funding Highlights</h2>'
            f"{_funding_cards(sections.get('funding highlights', ''))}"
            "</td></tr></table>"
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="margin:0 0 16px;border:1px solid #e2e8f0;border-radius:12px;'
            'background:#ffffff;">'
            '<tr><td style="padding:18px 20px;">'
            '<h2 style="margin:0 0 12px;font-size:18px;color:#0f172a;'
            'letter-spacing:-0.02em;">Ecosystem Moves</h2>'
            f"{_bullet_list(sections.get('ecosystem moves', ''))}"
            "</td></tr></table>"
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="margin:0 0 8px;border:1px solid #e2e8f0;border-radius:12px;'
            'background:#ffffff;">'
            '<tr><td style="padding:18px 20px;">'
            '<h2 style="margin:0 0 12px;font-size:18px;color:#0f172a;'
            'letter-spacing:-0.02em;">Trends to Watch</h2>'
            f"{_trend_cards(sections.get('trends to watch', ''))}"
            "</td></tr></table>"
        )
    else:
        safe = html.escape(body or "").replace("\n", "<br>")
        body_html = (
            f'<h1 style="margin:0 0 16px;font-size:22px;color:#0f172a;">{title}</h1>'
            f'<div style="font-size:15px;line-height:1.7;color:#334155;">{safe}</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Inter,Segoe UI,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;">
          <tr>
            <td style="padding:18px 20px;border-radius:12px 12px 0 0;background:#0f172a;">
              <p style="margin:0;font-size:18px;font-weight:700;color:#f8fafc;letter-spacing:-0.02em;">Signal</p>
              <p style="margin:4px 0 0;font-size:12px;color:#94a3b8;">Indian Startup Intelligence</p>
            </td>
          </tr>
          <tr>
            <td style="padding:22px 18px;background:#f8fafc;border-left:1px solid #e2e8f0;border-right:1px solid #e2e8f0;">
              {body_html}
            </td>
          </tr>
          <tr>
            <td style="padding:16px 20px 20px;border-radius:0 0 12px 12px;background:#0f172a;border-top:1px solid #1e293b;">
              <p style="margin:0 0 4px;font-size:12px;color:#cbd5e1;">Generated by Signal</p>
              <p style="margin:0;font-size:11px;color:#94a3b8;">Generation date: {html.escape(date_label)} · Graph version: {html.escape(version)}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _build_message(
    *,
    sender: str,
    recipient: str,
    body: str,
    graph_version: str = "",
) -> MIMEMultipart:
    subject = f"Signal Weekly Briefing - {datetime.now().strftime('%b %d, %Y')}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    # Plain-text part preserves original synthesis content (no content rewrite).
    text_part = MIMEText(body or "", _charset="utf-8")
    html_part = MIMEText(
        _render_briefing_html(body or "", graph_version=graph_version),
        "html",
        _charset="utf-8",
    )
    msg.attach(text_part)
    msg.attach(html_part)
    return msg


def _send_once(sender: str, password: str, recipient: str, msg: MIMEMultipart) -> None:
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
    # TEMP DEBUG SIG-024C — before Gmail env / SMTP work
    load_dotenv()
    logger.warning(
        "[SIG-024C DEBUG] BEFORE delivery state.keys=%s delivery_status=%s "
        "GMAIL_ADDRESS_present=%s GMAIL_APP_PASSWORD_present=%s pid=%s",
        sorted(state.keys()) if hasattr(state, "keys") else type(state),
        state.get("delivery_status"),
        bool((os.getenv("GMAIL_ADDRESS") or "").strip()),
        bool((os.getenv("GMAIL_APP_PASSWORD") or "").strip()),
        os.getpid(),
    )
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
    graph_version = str(state.get("graph_version") or os.getenv("GRAPH_VERSION") or "1.0")
    msg = _build_message(
        sender=sender,
        recipient=recipient,
        body=body,
        graph_version=graph_version,
    )

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
