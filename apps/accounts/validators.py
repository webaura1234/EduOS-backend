"""
Validators for the accounts app.

Reusable validation functions used by serializers and interactors.
"""

import re

from django.core.exceptions import ValidationError


def validate_phone_number(value: str) -> str:
    """
    Validate and normalise an Indian mobile number.

    Accepts:
      - +91XXXXXXXXXX  (E.164)
      - 91XXXXXXXXXX
      - 0XXXXXXXXXX
      - XXXXXXXXXX     (10 digits, assumed India)

    Returns the number in E.164 format (+91XXXXXXXXXX).
    Raises ValidationError if the number is invalid.
    """
    cleaned = re.sub(r"[\s\-\(\)]", "", value)

    # Strip country code prefix
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    elif cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0"):
        cleaned = cleaned[1:]

    if not re.fullmatch(r"[6-9]\d{9}", cleaned):
        raise ValidationError(
            "Enter a valid 10-digit Indian mobile number (e.g. +919876543210)."
        )

    return f"+91{cleaned}"


def validate_password_strength(value: str) -> str:
    """
    Enforce password complexity rules:
      - At least 8 characters
      - At least one uppercase letter
      - At least one digit
      - At least one special character (!@#$%^&*...)

    Raises ValidationError listing all failures at once.
    """
    errors = []

    if len(value) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", value):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"\d", value):
        errors.append("Password must contain at least one digit.")
    if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>?/\\|`~]", value):
        errors.append("Password must contain at least one special character.")

    if errors:
        raise ValidationError(errors)

    return value
