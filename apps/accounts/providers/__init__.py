"""
OTP provider factory.

Usage:
    from apps.accounts.providers import get_otp_provider
    result = get_otp_provider().send_sms_otp(mobile, message)

Set OTP_PROVIDER in settings to switch implementations ('msg91' is the default).
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.accounts.providers.base import OTPProvider

_provider: "OTPProvider | None" = None


def get_otp_provider() -> "OTPProvider":
    global _provider
    if _provider is None:
        from django.conf import settings
        name = getattr(settings, "OTP_PROVIDER", "msg91")
        if name == "msg91":
            from apps.accounts.providers.msg91 import MSG91Provider
            _provider = MSG91Provider()
        else:
            raise ValueError(f"Unknown OTP_PROVIDER setting: {name!r}")
    return _provider
