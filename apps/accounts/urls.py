"""
URL configuration for the accounts app.

All routes are under /api/v1/auth/ (see config/urls.py).
"""

from django.urls import path

from apps.accounts.views.auth import (
    LinkedAccountsView,
    LoginDisambiguateView,
    LoginView,
    LogoutView,
    MeView,
    PlatformLoginView,
    RefreshView,
    SwitchLinkedAccountView,
)
from apps.accounts.views.admins import SuperAdminAdminsView, SuperAdminAdminDetailView
from apps.accounts.views.invite import AcceptInviteView, CreateInviteView
from apps.accounts.views.password import (
    ForceChangePasswordView,
    OTPCheckView,
    OTPRequestView,
    OTPVerifyView,
    ResetAccountsView,
)
from apps.accounts.views.user import AdminResetPasswordView
from apps.accounts.views.users_management import (
    CheckMultiRoleView,
    UserManagementActionView,
    UserManagementView,
)
from apps.accounts.views.guardians import (
    AdminGuardianActionView,
    AdminGuardianOverviewView,
)
from apps.accounts.views.student_dashboard import StudentDashboardView
from apps.accounts.views.student_profile import StudentProfileFormView
from apps.accounts.views.faculty_dashboard import FacultyDashboardView

app_name = "accounts"

urlpatterns = [
    # ── Core auth ─────────────────────────────────────────────────────────
    path("login/",              LoginView.as_view(),             name="login"),
    path("platform/login/",     PlatformLoginView.as_view(),     name="platform-login"),
    path("login/disambiguate/", LoginDisambiguateView.as_view(), name="login-disambiguate"),
    path("refresh/",            RefreshView.as_view(),           name="refresh"),
    path("logout/",             LogoutView.as_view(),            name="logout"),
    path("me/",                 MeView.as_view(),                name="me"),
    path("me/dashboard/",       StudentDashboardView.as_view(),  name="student-dashboard"),
    path("me/student-profile/", StudentProfileFormView.as_view(), name="student-profile-form"),
    path("me/faculty-dashboard/", FacultyDashboardView.as_view(), name="faculty-dashboard"),
    path("linked-accounts/",    LinkedAccountsView.as_view(),    name="linked-accounts"),
    path("switch-linked/",      SwitchLinkedAccountView.as_view(), name="switch-linked"),

    # ── Password management ───────────────────────────────────────────────
    path("password/change/",         ForceChangePasswordView.as_view(), name="password-change"),
    path("password/reset/accounts/", ResetAccountsView.as_view(),       name="reset-accounts"),
    path("password/reset/request/",   OTPRequestView.as_view(),          name="otp-request"),
    path("password/reset/check-otp/", OTPCheckView.as_view(),            name="otp-check"),
    path("password/reset/verify/",    OTPVerifyView.as_view(),           name="otp-verify"),

    # ── Invite (onboarding) ───────────────────────────────────────────────
    path("invite/create/",  CreateInviteView.as_view(),  name="invite-create"),
    path("invite/accept/",  AcceptInviteView.as_view(),  name="invite-accept"),

    # ── Admin user actions ────────────────────────────────────────────────
    path("guardians/overview/", AdminGuardianOverviewView.as_view(), name="guardians-overview"),
    path("guardians/actions/", AdminGuardianActionView.as_view(), name="guardians-actions"),
    path("users/management/", UserManagementView.as_view(), name="users-management"),
    path("users/management/actions/", UserManagementActionView.as_view(), name="users-management-actions"),
    path("users/management/check-multi-role/", CheckMultiRoleView.as_view(), name="users-check-multi-role"),
    path("users/<uuid:user_id>/reset-password/", AdminResetPasswordView.as_view(), name="admin-reset-password"),

    # ── Super-admin branch-admin management ───────────────────────────────
    path("admins/",                 SuperAdminAdminsView.as_view(),      name="admins"),
    path("admins/<uuid:admin_id>/", SuperAdminAdminDetailView.as_view(), name="admin-detail"),
]
