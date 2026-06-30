"""
Email dispatch via MSG91 with a lightweight circuit breaker.

Mirrors the sms.py circuit-breaker pattern. In DEBUG/dev the message is
logged to the terminal. In production it calls the MSG91 email API v5.
"""

import logging

from django.conf import settings
from django.core.cache import cache

from apps.core.exceptions import ServiceUnavailableError

logger = logging.getLogger("apps.accounts.email")

_FAILURE_THRESHOLD = 5
_OPEN_SECONDS = 120
_FAIL_COUNT_KEY = "email:fail_count"
_OPEN_KEY = "email:circuit_open"


def _circuit_is_open() -> bool:
    return bool(cache.get(_OPEN_KEY))


def _record_success() -> None:
    cache.delete(_FAIL_COUNT_KEY)
    cache.delete(_OPEN_KEY)


def _record_failure() -> None:
    try:
        count = cache.incr(_FAIL_COUNT_KEY)
    except ValueError:
        cache.set(_FAIL_COUNT_KEY, 1, timeout=_OPEN_SECONDS)
        count = 1
    if count >= _FAILURE_THRESHOLD:
        cache.set(_OPEN_KEY, True, timeout=_OPEN_SECONDS)
        logger.error("Email circuit breaker OPENED after %d consecutive failures", count)


def send_email(to_email: str, to_name: str, subject: str, html_body: str, text_body: str = "") -> None:
    """
    Send a transactional email via MSG91.

    Raises ServiceUnavailableError if the circuit is open or the send fails.
    """
    if _circuit_is_open():
        logger.warning("Email circuit open — refusing to send to %s", to_email)
        raise ServiceUnavailableError(
            "Email service temporarily unavailable. Try again in a few minutes."
        )

    if settings.DEBUG:
        print(
            "\n============== [DEV EMAIL — not actually sent] ==============\n"
            f"  To:      {to_email} ({to_name})\n"
            f"  Subject: {subject}\n"
            f"  Body:    {text_body or html_body}\n"
            "=============================================================\n",
            flush=True,
        )
        logger.info("📧 [DEV EMAIL] to %s: %s", to_email, subject)
        _record_success()
        return

    try:
        import requests

        auth_key = getattr(settings, "MSG91_AUTH_KEY", "")
        from_email = getattr(settings, "MSG91_EMAIL_FROM", "noreply@eduerp.in")
        from_name = getattr(settings, "MSG91_EMAIL_FROM_NAME", "EduOS")
        domain = getattr(settings, "MSG91_EMAIL_DOMAIN", "eduerp.in")

        payload = {
            "to": [{"email": to_email, "name": to_name}],
            "from": {"email": from_email, "name": from_name},
            "domain": domain,
            "subject": subject,
            "body_html": html_body,
            "body_text": text_body or subject,
        }

        requests.post(
            "https://api.msg91.com/api/v5/email/send",
            json=payload,
            headers={"authkey": auth_key, "Content-Type": "application/json"},
            timeout=10,
        ).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.error("Email send failed to %s: %s", to_email, exc)
        _record_failure()
        raise ServiceUnavailableError(
            "Email service temporarily unavailable. Try again in a few minutes."
        )

    _record_success()
    logger.info("Email sent to %s: %s", to_email, subject)


def send_mfa_otp_email(to_email: str, to_name: str, otp: str) -> None:
    """Send the MFA login verification code to the user's email."""
    subject = "Your EduOS Login Verification Code"
    html_body = (
        f"<p>Hello {to_name},</p>"
        f"<p>Your EduOS login verification code is:</p>"
        f"<h2 style='letter-spacing:4px;font-family:monospace'>{otp}</h2>"
        f"<p>This code expires in <strong>10 minutes</strong>.</p>"
        f"<p>If you did not attempt to log in, please contact your administrator immediately.</p>"
        f"<p>— The EduOS Team</p>"
    )
    text_body = (
        f"Hello {to_name},\n\n"
        f"Your EduOS login verification code is: {otp}\n\n"
        f"This code expires in 10 minutes.\n\n"
        f"If you did not attempt to log in, please contact your administrator immediately.\n\n"
        f"— The EduOS Team"
    )
    send_email(to_email, to_name, subject, html_body, text_body)
