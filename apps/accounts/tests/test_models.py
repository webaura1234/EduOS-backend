import pytest
from datetime import timedelta
from django.utils import timezone
from django.db import IntegrityError

from apps.accounts.models.user import Role, User
from apps.accounts.models.token import RefreshToken, OTPRecord, InviteToken
from apps.accounts.models.security import LoginAttempt
from apps.accounts.tests.factories import UserFactory, RefreshTokenFactory, OTPRecordFactory, InviteTokenFactory, LoginAttemptFactory


def test_user_properties(tenant, branch):
    # Student logs in via custom_login_id
    student = UserFactory(
        role=Role.STUDENT,
        custom_login_id="S123",
        phone="+919876543210",
        tenant=tenant,
        branch=branch
    )
    assert student.login_identifier == "S123"
    assert student.full_name == f"{student.first_name} {student.last_name}".strip()

    # Admin logs in via phone
    admin = UserFactory(
        role=Role.ADMIN,
        custom_login_id="A123",
        phone="+919876543211",
        tenant=tenant,
        branch=branch
    )
    assert admin.login_identifier == "+919876543211"


def test_unique_custom_login_id_per_tenant(tenant, branch):
    # Create first student
    UserFactory(
        role=Role.STUDENT,
        custom_login_id="SAME_ID",
        tenant=tenant,
        branch=branch
    )

    # Creating second student with same custom_login_id in SAME tenant should fail integrity check
    with pytest.raises(IntegrityError):
        UserFactory(
            role=Role.STUDENT,
            custom_login_id="SAME_ID",
            tenant=tenant,
            branch=branch
        )


def test_custom_login_id_uniqueness_across_different_tenants(tenant, branch):
    # Student in tenant 1
    UserFactory(
        role=Role.STUDENT,
        custom_login_id="SAME_ID",
        tenant=tenant,
        branch=branch
    )

    # Student in tenant 2
    from apps.organizations.tests.factories import TenantFactory, BranchFactory
    other_tenant = TenantFactory()
    other_branch = BranchFactory(tenant=other_tenant)

    other_student = UserFactory(
        role=Role.STUDENT,
        custom_login_id="SAME_ID",
        tenant=other_tenant,
        branch=other_branch
    )
    assert other_student.id is not None


def test_refresh_token_validity():
    token = RefreshTokenFactory()
    assert token.is_valid is True
    assert token.is_expired is False

    # Revoke
    token.is_revoked = True
    token.save()
    assert token.is_valid is False

    # Expire
    token.is_revoked = False
    token.expires_at = timezone.now() - timedelta(seconds=1)
    token.save()
    assert token.is_valid is False
    assert token.is_expired is True


def test_otp_record_validity():
    otp = OTPRecordFactory()
    assert otp.is_valid is True
    assert otp.is_expired is False

    # Use
    otp.is_used = True
    otp.save()
    assert otp.is_valid is False

    # Expire
    otp.is_used = False
    otp.expires_at = timezone.now() - timedelta(seconds=1)
    otp.save()
    assert otp.is_valid is False
    assert otp.is_expired is True


def test_invite_token_validity():
    invite = InviteTokenFactory()
    assert invite.is_valid is True
    assert invite.is_expired is False

    # Use
    invite.is_used = True
    invite.save()
    assert invite.is_valid is False

    # Expire
    invite.is_used = False
    invite.expires_at = timezone.now() - timedelta(seconds=1)
    invite.save()
    assert invite.is_valid is False
    assert invite.is_expired is True
