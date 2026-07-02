"""MSG91Provider — wraps the existing email.py / sms.py circuit-breaker dispatchers."""

from apps.accounts.providers.base import OTPProvider, OTPSendResult


class MSG91Provider(OTPProvider):
    @property
    def provider_name(self) -> str:
        return "msg91"

    def send_sms_otp(self, mobile: str, message: str) -> OTPSendResult:
        from apps.accounts.sms import send_sms
        from apps.core.exceptions import ServiceUnavailableError
        try:
            send_sms(mobile, message)
            return OTPSendResult(success=True)
        except ServiceUnavailableError as exc:
            return OTPSendResult(success=False, error_code="service_unavailable", error_message=str(exc))
        except Exception as exc:  # noqa: BLE001
            return OTPSendResult(success=False, error_message=str(exc))

    def send_email_otp(self, email: str, name: str, otp: str) -> OTPSendResult:
        from apps.accounts.email import send_mfa_otp_email
        from apps.core.exceptions import ServiceUnavailableError
        try:
            send_mfa_otp_email(email, name, otp)
            return OTPSendResult(success=True)
        except ServiceUnavailableError as exc:
            return OTPSendResult(success=False, error_code="service_unavailable", error_message=str(exc))
        except Exception as exc:  # noqa: BLE001
            return OTPSendResult(success=False, error_message=str(exc))
