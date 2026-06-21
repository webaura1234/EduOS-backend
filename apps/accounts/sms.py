"""
SMS dispatch with a lightweight circuit breaker (EC-AUTH-16).

In DEBUG/dev the message is logged and treated as sent. In production the
message is sent via MSG91. Repeated failures open the circuit so that
subsequent sends fail fast with a friendly ServiceUnavailableError instead of
hammering a downstream that is already down — and crucially, no OTP/invite is
dispatched while the circuit is open.
"""

import logging

from django.conf import settings
from django.core.cache import cache

from apps.core.exceptions import ServiceUnavailableError

logger = logging.getLogger("apps.accounts.sms")

# Circuit breaker tuning
_FAILURE_THRESHOLD = 5          # consecutive failures before the circuit opens
_OPEN_SECONDS = 120             # how long the circuit stays open
_FAIL_COUNT_KEY = "sms:fail_count"
_OPEN_KEY = "sms:circuit_open"


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
        logger.error("SMS circuit breaker OPENED after %d consecutive failures", count)


def send_sms(phone: str, message: str) -> None:
    """Send an SMS, honouring the circuit breaker.

    Raises ServiceUnavailableError if the circuit is open or the send fails.
    """
    if _circuit_is_open():
        logger.warning("SMS circuit open — refusing to send to %s", phone)
        raise ServiceUnavailableError(
            "SMS service temporarily unavailable. Try again in a few minutes."
        )

    if settings.DEBUG:
        # Dev: no real SMS is sent — print the message (incl. any OTP) straight to the
        # server terminal so developers can read the code during local testing.
        print(
            "\n============== [DEV SMS — not actually sent] ==============\n"
            f"  To:      {phone}\n"
            f"  Message: {message}\n"
            "===========================================================\n",
            flush=True,
        )
        logger.info("📩 [DEV SMS] to %s: %s", phone, message)
        _record_success()
        return

    try:
        import requests

        requests.post(
            "https://api.msg91.com/api/sendhttp.php",
            params={
                "authkey": settings.MSG91_AUTH_KEY,
                "mobiles": phone,
                "message": message,
                "sender": getattr(settings, "MSG91_SENDER_ID", ""),
                "route": "4",
            },
            timeout=10,
        ).raise_for_status()
    except Exception as exc:  # noqa: BLE001 — any failure trips the breaker
        logger.error("SMS send failed to %s: %s", phone, exc)
        _record_failure()
        raise ServiceUnavailableError(
            "SMS service temporarily unavailable. Try again in a few minutes."
        )

    _record_success()
    logger.info("SMS sent to %s", phone)
