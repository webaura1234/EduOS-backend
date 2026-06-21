"""Dev-mode SMS prints the OTP to the terminal (no real send)."""

import pytest
from django.test import override_settings

from apps.accounts.sms import send_sms

pytestmark = pytest.mark.django_db


@override_settings(DEBUG=True)
def test_dev_sms_prints_otp_to_terminal(capsys):
    send_sms("+919800000123", "Your EduOS password reset code is 482913. It expires in 5 minutes.")
    out = capsys.readouterr().out
    assert "DEV SMS" in out
    assert "482913" in out  # the OTP is visible in the terminal output
    assert "+919800000123" in out
