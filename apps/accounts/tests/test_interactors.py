import pytest
from unittest.mock import patch
from datetime import timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.accounts.interactors import auth as auth_interactor
from apps.accounts.interactors import password as password_interactor
from apps.accounts.interactors import invite as invite_interactor

from apps.accounts.models.user import Role
from apps.accounts.models.token import OTPRecord, InviteToken, RefreshToken
from apps.accounts.tests.factories import UserFactory, RefreshTokenFactory, OTPRecordFactory, InviteTokenFactory, LoginAttemptFactory
from apps.organizations.tests.factories import TenantFactory, BranchFactory
from apps.accounts.dtos import LoginResponseDTO, TokenPairDTO, InviteCreatedDTO, InviteAcceptedDTO


# ─────────────────────────────────────────────────────────────────────────────
# Auth Interactor Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_login_success(tenant, branch):
    user = UserFactory(
        role=Role.STUDENT,
        custom_login_id="S123",
        password="TestPass123!",
        tenant=tenant,
        branch=branch,
        must_change_password=True,
    )

    result = auth_interactor.login(
        identifier="S123",
        password="TestPass123!",
        role=Role.STUDENT,
        tenant_id=tenant.id,
        device_info="iPhone",
        ip_address="127.0.0.1",
    )

    assert isinstance(result, LoginResponseDTO)
    assert result.must_change_password is True
    assert result.user_id == user.id
    assert result.role == Role.STUDENT
    assert result.access is not None
    assert result.refresh is not None


def test_login_invalid_password(tenant, branch):
    UserFactory(
        role=Role.ADMIN,
        phone="+919876543210",
        password="CorrectPassword123!",
        tenant=tenant,
        branch=branch,
    )

    with pytest.raises(AuthenticationFailed):
        auth_interactor.login(
            identifier="+919876543210",
            password="WrongPassword!",
            role=Role.ADMIN,
            tenant_id=tenant.id,
        )


def test_login_lockout_trigger(tenant, branch):
    phone = "+919876543210"
    UserFactory(
        role=Role.ADMIN,
        phone=phone,
        password="CorrectPassword123!",
        tenant=tenant,
        branch=branch,
    )

    # 5 failed attempts
    for _ in range(5):
        with pytest.raises(AuthenticationFailed):
            auth_interactor.login(
                identifier=phone,
                password="WrongPassword!",
                role=Role.ADMIN,
                tenant_id=tenant.id,
            )

    # 6th attempt is locked out instantly
    with pytest.raises(PermissionDenied) as exc:
        auth_interactor.login(
            identifier=phone,
            password="CorrectPassword123!",
            role=Role.ADMIN,
            tenant_id=tenant.id,
        )
    assert "Too many failed attempts" in str(exc.value)


def test_refresh_token_success():
    from apps.accounts.tokens import generate_refresh_token
    user = UserFactory(is_active=True)
    token_str, rt = generate_refresh_token(user)

    result = auth_interactor.refresh_tokens(token_str)
    assert isinstance(result, TokenPairDTO)
    assert result.access is not None
    assert result.refresh is not None

    # Verify rotation: old token is revoked
    rt.refresh_from_db()
    assert rt.is_revoked is True


def test_refresh_token_revoked():
    from apps.accounts.tokens import generate_refresh_token
    user = UserFactory(is_active=True)
    token_str, rt = generate_refresh_token(user)
    rt.is_revoked = True
    rt.save()

    with pytest.raises(AuthenticationFailed):
        auth_interactor.refresh_tokens(token_str)


def test_logout():
    rt = RefreshTokenFactory(token="active-token")
    auth_interactor.logout("active-token")
    rt.refresh_from_db()
    assert rt.is_revoked is True


# ─────────────────────────────────────────────────────────────────────────────
# Password Interactor Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_force_change_password_success(tenant, branch):
    user = UserFactory(
        role=Role.STUDENT,
        password="OldPassword123!",
        must_change_password=True,
        tenant=tenant,
        branch=branch,
    )
    RefreshTokenFactory(user=user, token="token-to-revoke")

    password_interactor.force_change_password(user, "OldPassword123!", "NewPass321!")
    user.refresh_from_db()
    assert user.must_change_password is False
    assert user.check_password("NewPass321!") is True

    # Tokens are revoked
    assert RefreshToken.objects.get(token="token-to-revoke").is_revoked is True


def test_force_change_password_wrong_current(tenant, branch):
    user = UserFactory(
        role=Role.STUDENT,
        password="OldPassword123!",
        must_change_password=True,
        tenant=tenant,
        branch=branch,
    )
    with pytest.raises(AuthenticationFailed):
        password_interactor.force_change_password(user, "WrongPassword!", "NewPass321!")


def test_force_change_password_strength_check(tenant, branch):
    user = UserFactory(
        role=Role.STUDENT,
        password="OldPassword123!",
        must_change_password=True,
        tenant=tenant,
        branch=branch,
    )
    with pytest.raises(ValidationError):
        password_interactor.force_change_password(user, "OldPassword123!", "short")


def test_force_change_password_same_as_old(tenant, branch):
    user = UserFactory(
        role=Role.STUDENT,
        password="OldPassword123!",
        must_change_password=True,
        tenant=tenant,
        branch=branch,
    )
    with pytest.raises(ValidationError):
        password_interactor.force_change_password(user, "OldPassword123!", "OldPassword123!")


@patch("apps.accounts.interactors.password._send_otp")
def test_request_otp_reset(mock_send, tenant, branch):
    phone = "+919876543210"
    user = UserFactory(
        role=Role.ADMIN,
        phone=phone,
        tenant=tenant,
        branch=branch,
    )

    password_interactor.request_otp_reset(phone, tenant.id)
    assert mock_send.called
    assert OTPRecord.objects.filter(user=user, phone=phone).exists()


@patch("apps.accounts.interactors.password._send_otp")
def test_request_otp_reset_rate_limit(mock_send, tenant, branch):
    phone = "+919876543210"
    UserFactory(
        role=Role.ADMIN,
        phone=phone,
        tenant=tenant,
        branch=branch,
    )

    # 3 OTPs (limit)
    for _ in range(3):
        password_interactor.request_otp_reset(phone, tenant.id)

    # 4th triggers PermissionDenied rate limit
    with pytest.raises(PermissionDenied):
        password_interactor.request_otp_reset(phone, tenant.id)


def test_verify_otp_and_reset_success(tenant, branch):
    phone = "+919876543210"
    user = UserFactory(
        role=Role.ADMIN,
        phone=phone,
        password="OldPassword123!",
        tenant=tenant,
        branch=branch,
    )
    # Hashed OTP in DB, plain is '123456'
    otp_hash = password_interactor._hash_otp("123456")
    otp_rec = OTPRecordFactory(user=user, phone=phone, otp_hash=otp_hash)

    password_interactor.verify_otp_and_reset(phone, "123456", "NewSecurePass321!", tenant.id)

    user.refresh_from_db()
    otp_rec.refresh_from_db()
    assert user.check_password("NewSecurePass321!") is True
    assert otp_rec.is_used is True


def test_verify_otp_and_reset_wrong_otp(tenant, branch):
    phone = "+919876543210"
    user = UserFactory(
        role=Role.ADMIN,
        phone=phone,
        tenant=tenant,
        branch=branch,
    )
    otp_hash = password_interactor._hash_otp("123456")
    OTPRecordFactory(user=user, phone=phone, otp_hash=otp_hash)

    with pytest.raises(AuthenticationFailed):
        password_interactor.verify_otp_and_reset(phone, "wrong_otp", "NewSecurePass321!", tenant.id)


# ─────────────────────────────────────────────────────────────────────────────
# Invite Interactor Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_create_and_send_invite_success(tenant, branch):
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch)

    result = invite_interactor.create_and_send_invite(
        created_by=admin,
        role=Role.FACULTY,
        first_name="Ramesh",
        custom_login_id="EMP101",
        tenant_id=tenant.id,
    )

    assert isinstance(result, InviteCreatedDTO)
    assert result.user_id is not None
    assert result.invite_token is not None

    # Verify token exists in DB
    assert InviteToken.objects.filter(token=result.invite_token, user_id=result.user_id).exists()


def test_create_and_send_invite_unauthorized(tenant, branch):
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch)

    with pytest.raises(PermissionDenied):
        invite_interactor.create_and_send_invite(
            created_by=student,
            role=Role.FACULTY,
            first_name="Ramesh",
            custom_login_id="EMP101",
            tenant_id=tenant.id,
        )


def test_accept_invite_success(tenant, branch):
    student = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        must_change_password=True,
    )
    student.set_unusable_password()
    student.save()

    invite = InviteTokenFactory(user=student, is_used=False)

    result = invite_interactor.accept_invite(
        token_uuid=invite.token,
        new_password="NewSecurePassword123!",
    )

    assert isinstance(result, InviteAcceptedDTO)
    assert result.access is not None
    assert result.refresh is not None
    assert result.user_id == student.id

    student.refresh_from_db()
    invite.refresh_from_db()
    assert student.check_password("NewSecurePassword123!") is True
    assert student.must_change_password is False
    assert invite.is_used is True
