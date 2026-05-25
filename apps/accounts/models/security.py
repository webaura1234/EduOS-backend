"""
Security and authentication models.

Groups together models related to auth security:
  - LoginAttempt    → rate-limit brute-force protection
  - UserSession     → active session tracking (device / IP)
  - MFADevice       → TOTP / SMS-based second factor devices
  - StepUpAuth      → temporary elevated-privilege token
  - PasswordReset   → admin-initiated password reset tokens
"""

# TODO: Implement models in this file.
# Suggested models: LoginAttempt, UserSession, MFADevice, StepUpAuth, PasswordReset
