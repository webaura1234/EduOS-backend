"""
URL configuration for the accounts app.

All routes are under /api/v1/auth/ (see config/urls.py).
"""

from django.urls import path

from apps.accounts.views.auth import (
    LoginDisambiguateView,
    LoginView,
    LogoutView,
    MeView,
    RefreshView,
)
from apps.accounts.views.invite import AcceptInviteView, CreateInviteView
from apps.accounts.views.password import (
    ForceChangePasswordView,
    OTPRequestView,
    OTPVerifyView,
    ResetAccountsView,
)
from apps.accounts.views.user import AdminResetPasswordView

app_name = "accounts"

urlpatterns = [
    # ── Core auth ─────────────────────────────────────────────────────────
    path("login/",              LoginView.as_view(),             name="login"),
    path("login/disambiguate/", LoginDisambiguateView.as_view(), name="login-disambiguate"),
    path("refresh/",            RefreshView.as_view(),           name="refresh"),
    path("logout/",             LogoutView.as_view(),            name="logout"),
    path("me/",                 MeView.as_view(),                name="me"),

    # ── Password management ───────────────────────────────────────────────
    path("password/change/",         ForceChangePasswordView.as_view(), name="password-change"),
    path("password/reset/accounts/", ResetAccountsView.as_view(),       name="reset-accounts"),
    path("password/reset/request/",  OTPRequestView.as_view(),          name="otp-request"),
    path("password/reset/verify/",   OTPVerifyView.as_view(),           name="otp-verify"),

    # ── Invite (onboarding) ───────────────────────────────────────────────
    path("invite/create/",  CreateInviteView.as_view(),  name="invite-create"),
    path("invite/accept/",  AcceptInviteView.as_view(),  name="invite-accept"),

    # ── Admin user actions ────────────────────────────────────────────────
    path("users/<uuid:user_id>/reset-password/", AdminResetPasswordView.as_view(), name="admin-reset-password"),
]
