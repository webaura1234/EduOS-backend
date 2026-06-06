"""
Edge-case coverage for the accounts module, mapped to PRD EC-AUTH-* cases.

Each test names the EC-AUTH id it verifies.
"""

import uuid
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.interactors.auth import disambiguate_login, login
from apps.accounts.interactors.invite import accept_invite, create_and_send_invite
from apps.accounts.interactors.password import request_otp_reset
from apps.accounts.models.token import InviteToken
from apps.accounts.models.user import Role, User
from apps.accounts.models.token import OTPRecord
from apps.accounts.tests.factories import UserFactory
from apps.core.exceptions import GoneError, ServiceUnavailableError
from apps.organizations.tests.factories import TenantFactory, BranchFactory

from django.core.exceptions import ValidationError
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

pytestmark = pytest.mark.django_db

PW = "TestPass123!"


# ── EC-AUTH-04: role changed in DB → next API call 401 ────────────────────────
def test_ec_auth_04_role_change_invalidates_token(api_client, admin_user):
    from apps.accounts.tokens import generate_access_token

    token = generate_access_token(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    # Role changes in the DB after the token was issued.
    admin_user.role = Role.SUPER_ADMIN
    admin_user.save(update_fields=["role"])

    resp = api_client.get(reverse("accounts:me"))
    assert resp.status_code == 401


# ── EC-AUTH-10: deactivated user → 401 ────────────────────────────────────────
def test_ec_auth_10_deactivated_user_rejected(api_client, admin_user):
    from apps.accounts.tokens import generate_access_token

    token = generate_access_token(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    admin_user.is_active = False
    admin_user.save(update_fields=["is_active"])

    resp = api_client.get(reverse("accounts:me"))
    assert resp.status_code == 401


# ── EC-AUTH-08: invite reused → 410 Gone + used_at stamped ────────────────────
def test_ec_auth_08_invite_reuse_returns_410(tenant, branch):
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919800000001")
    dto = create_and_send_invite(
        created_by=admin, role=Role.FACULTY, first_name="Fac",
        custom_login_id="FAC-RE", tenant_id=tenant.id, branch_id=branch.id,
    )
    accept_invite(token_uuid=dto.invite_token, new_password=PW)

    invite = InviteToken.objects.get(token=dto.invite_token)
    assert invite.is_used and invite.used_at is not None

    with pytest.raises(GoneError):
        accept_invite(token_uuid=dto.invite_token, new_password=PW)


# ── EC-AUTH-09: invite expired → 410 Gone ─────────────────────────────────────
def test_ec_auth_09_invite_expired_returns_410(tenant, branch):
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919800000002")
    dto = create_and_send_invite(
        created_by=admin, role=Role.FACULTY, first_name="Fac",
        custom_login_id="FAC-EXP", tenant_id=tenant.id, branch_id=branch.id,
    )
    InviteToken.objects.filter(token=dto.invite_token).update(
        expires_at=timezone.now() - timedelta(hours=1)
    )
    with pytest.raises(GoneError):
        accept_invite(token_uuid=dto.invite_token, new_password=PW)


# ── EC-AUTH-11: phone shared by admin + parent → role picker ──────────────────
def test_ec_auth_11_login_disambiguation(tenant, branch):
    shared_phone = "+919811111111"
    group = uuid.uuid4()
    UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch,
                phone=shared_phone, linked_user_group_id=group, custom_login_id=None)
    UserFactory(role=Role.PARENT, tenant=tenant, branch=branch,
                phone=shared_phone, linked_user_group_id=group, custom_login_id=None)

    result = disambiguate_login(identifier=shared_phone, password=PW, tenant_id=str(tenant.id))
    assert result.requires_selection is True
    assert {a["role"] for a in result.accounts} == {Role.ADMIN, Role.PARENT}
    assert result.login is None  # no token issued before selection


def test_ec_auth_11_single_match_logs_in(tenant, branch):
    UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch,
                phone="+919812222222", custom_login_id=None)
    result = disambiguate_login(identifier="+919812222222", password=PW, tenant_id=str(tenant.id))
    assert result.requires_selection is False
    assert result.login is not None and result.login.access


# ── EC-AUTH-12/20: reset phone matches multiple accounts → picker + targeting ──
def test_ec_auth_12_reset_account_picker(tenant, branch, monkeypatch):
    monkeypatch.setattr("apps.accounts.interactors.password.send_sms", lambda *a, **k: None)
    guardian_phone = "+919813333333"
    UserFactory(role=Role.PARENT, tenant=tenant, branch=branch, phone=guardian_phone, custom_login_id=None)
    UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, phone=guardian_phone, custom_login_id="STU-G1")

    from apps.accounts.interactors.password import list_reset_accounts
    accounts = list_reset_accounts(guardian_phone, str(tenant.id))
    assert len(accounts) == 2

    # No account selected → ValidationError (disambiguation required)
    with pytest.raises(ValidationError):
        request_otp_reset(phone=guardian_phone, tenant_id=str(tenant.id))

    # With a selected account → OTP issued for that account
    target_id = accounts[0]["user_id"]
    request_otp_reset(phone=guardian_phone, tenant_id=str(tenant.id), account_id=target_id)
    assert OTPRecord.objects.filter(user_id=target_id).count() == 1


# ── EC-AUTH-13: invite phone matches existing user → linked account ───────────
def test_ec_auth_13_linked_account_on_invite(tenant, branch):
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919814444444")
    existing = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                           phone="+919815555555", custom_login_id="FAC-LINK")

    dto = create_and_send_invite(
        created_by=admin, role=Role.PARENT, first_name="Linked",
        phone="+919815555555", tenant_id=tenant.id, branch_id=branch.id,
    )
    assert dto.linked_account_created is True

    existing.refresh_from_db()
    new_user = User.objects.get(id=dto.user_id)
    assert existing.linked_user_group_id is not None
    assert existing.linked_user_group_id == new_user.linked_user_group_id


# ── EC-AUTH-16: SMS gateway down → 503, no OTP persisted ─────────────────────
def test_ec_auth_16_sms_failure_no_otp(tenant, branch, monkeypatch):
    UserFactory(role=Role.PARENT, tenant=tenant, branch=branch, phone="+919816666666", custom_login_id=None)

    def boom(*args, **kwargs):
        raise ServiceUnavailableError("down")

    monkeypatch.setattr("apps.accounts.interactors.password.send_sms", boom)

    with pytest.raises(ServiceUnavailableError):
        request_otp_reset(phone="+919816666666", tenant_id=str(tenant.id))

    assert OTPRecord.objects.count() == 0  # nothing persisted on failed dispatch


# ── EC-AUTH-21: admin manual password reset → temp pw + forced change ─────────
def test_ec_auth_21_admin_reset(admin_auth_client, admin_user, tenant, branch):
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-RST")
    url = reverse("accounts:admin-reset-password", kwargs={"user_id": student.id})

    resp = admin_auth_client.post(url, {}, format="json")
    assert resp.status_code == 200
    body = resp.json().get("data", resp.json())
    assert body.get("temp_password")

    student.refresh_from_db()
    assert student.must_change_password is True


# ── EC-AUTH-25: lockout scoped to user, other users unaffected ────────────────
def test_ec_auth_25_lockout_scoped_to_user(tenant, branch):
    locked = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch, custom_login_id="FAC-LOCK")
    other = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch, custom_login_id="FAC-OK")

    for _ in range(5):
        with pytest.raises(AuthenticationFailed):
            login(identifier="FAC-LOCK", password="wrong", role=Role.FACULTY, tenant_id=str(tenant.id))

    # 6th attempt for the locked user → lockout (even with correct password)
    with pytest.raises(PermissionDenied):
        login(identifier="FAC-LOCK", password=PW, role=Role.FACULTY, tenant_id=str(tenant.id))

    # A different user is unaffected and can log in successfully.
    result = login(identifier="FAC-OK", password=PW, role=Role.FACULTY, tenant_id=str(tenant.id))
    assert result.access


# ── EC-AUTH-26: parent portal disabled → 403 ──────────────────────────────────
def test_ec_auth_26_parent_portal_disabled():
    tenant = TenantFactory(parent_access_enabled=False)
    branch = BranchFactory(tenant=tenant)
    UserFactory(role=Role.PARENT, tenant=tenant, branch=branch, phone="+919817777777", custom_login_id=None)

    with pytest.raises(PermissionDenied):
        login(identifier="+919817777777", password=PW, role=Role.PARENT, tenant_id=str(tenant.id))
