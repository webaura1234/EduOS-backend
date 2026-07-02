"""
OTPProvider ABC — defines the interface for sending OTPs via any channel.

The factory in providers/__init__.py reads OTP_PROVIDER from settings and
returns the correct concrete implementation. Swap providers by changing
a single settings key, zero other code changes.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class OTPSendResult:
    success: bool
    request_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class OTPProvider(ABC):
    @abstractmethod
    def send_sms_otp(self, mobile: str, message: str) -> OTPSendResult: ...

    @abstractmethod
    def send_email_otp(self, email: str, name: str, otp: str) -> OTPSendResult: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...
