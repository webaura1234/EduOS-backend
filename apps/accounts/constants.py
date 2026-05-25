"""
Constants for the accounts app.

All magic numbers related to auth security live here —
never hardcode these in business logic.
"""

# ── Brute-force protection ────────────────────────────────────────────────
MAX_LOGIN_ATTEMPTS = 5           # max failures before lockout
LOGIN_ATTEMPT_WINDOW_MINUTES = 30  # rolling window for counting failures
LOGIN_LOCKOUT_DURATION_MINUTES = 15  # how long to lock the identifier

# ── OTP (phone-based password reset) ─────────────────────────────────────
OTP_MAX_PER_WINDOW = 3           # max OTPs sent per phone per window
OTP_WINDOW_MINUTES = 30          # rolling window for OTP rate limit
OTP_LENGTH = 6                   # digits in the OTP
OTP_EXPIRY_MINUTES = 5           # OTP valid for 5 minutes after issue

# ── Invite token ─────────────────────────────────────────────────────────
INVITE_EXPIRY_HOURS = 48         # invite links expire in 48 hours
