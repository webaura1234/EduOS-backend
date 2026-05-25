import pytest
import uuid
from datetime import timedelta
from django.utils import timezone

from apps.accounts.queries import user as user_queries
from apps.accounts.queries import session as session_queries
from apps.accounts.tests.factories import UserFactory, RefreshTokenFactory, OTPRecordFactory, InviteTokenFactory, LoginAttemptFactory
from apps.accounts.models.user import Role


def test_get_user_by_id(tenant, branch):
    user = UserFactory(tenant=tenant, branch=branch, is_active=True)
    assert user_queries.get_user_by_id(user.id) == user

    inactive_user = UserFactory(tenant=tenant, branch=branch, is_active=False)
    assert user_queries.get_user_by_id(inactive_user.id) is None


def test_get_user_by_phone(tenant, branch):
    user = UserFactory(
        role=Role.ADMIN,
        phone="+919876543210",
        tenant=tenant,
        branch=branch,
        is_active=True
    )
    assert user_queries.get_user_by_phone("+919876543210", tenant.id) == user
    assert user_queries.get_user_by_phone("+919876543210", uuid.uuid4()) is None


def test_get_user_by_custom_login_id(tenant, branch):
    user = UserFactory(
        role=Role.STUDENT,
        custom_login_id="S123",
        tenant=tenant,
        branch=branch,
        is_active=True
    )
    assert user_queries.get_user_by_custom_login_id("S123", tenant.id) == user
    assert user_queries.get_user_by_custom_login_id("S123", uuid.uuid4()) is None


def test_get_active_refresh_token():
    rt = RefreshTokenFactory(token="active-token")
    assert user_queries.get_active_refresh_token("active-token") == rt

    # Revoked token
    rt_revoked = RefreshTokenFactory(token="revoked-token", is_revoked=True)
    assert user_queries.get_active_refresh_token("revoked-token") is None

    # Expired token
    rt_expired = RefreshTokenFactory(
        token="expired-token",
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert user_queries.get_active_refresh_token("expired-token") is None


def test_get_valid_otp(tenant, branch):
    user = UserFactory(tenant=tenant, branch=branch, phone="+919876543210")
    otp = OTPRecordFactory(user=user, phone="+919876543210", is_used=False)

    assert user_queries.get_valid_otp("+919876543210") == otp

    # Used OTP
    otp.is_used = True
    otp.save()
    assert user_queries.get_valid_otp("+919876543210") is None


def test_count_otps_in_window():
    phone = "+919876543210"
    user = UserFactory(phone=phone)

    # Clean initial state
    assert user_queries.count_otps_in_window(phone, 30) == 0

    OTPRecordFactory(user=user, phone=phone)
    OTPRecordFactory(user=user, phone=phone)
    assert user_queries.count_otps_in_window(phone, 30) == 2


def test_get_valid_invite():
    invite = InviteTokenFactory(is_used=False)
    assert user_queries.get_valid_invite(invite.token) == invite

    # Used
    invite.is_used = True
    invite.save()
    assert user_queries.get_valid_invite(invite.token) is None


def test_login_attempts(tenant):
    tenant_id = tenant.id
    assert user_queries.count_failed_attempts("test-user", tenant_id, 30) == 0

    user_queries.record_login_attempt("test-user", tenant_id, "127.0.0.1", False, "wrong_password")
    user_queries.record_login_attempt("test-user", tenant_id, "127.0.0.1", False, "wrong_password")
    user_queries.record_login_attempt("test-user", tenant_id, "127.0.0.1", True)

    # Only counts failures
    assert user_queries.count_failed_attempts("test-user", tenant_id, 30) == 2


def test_session_queries():
    # revoke_refresh_token
    rt = RefreshTokenFactory(token="session-token")
    assert session_queries.revoke_refresh_token("session-token") is True
    rt.refresh_from_db()
    assert rt.is_revoked is True

    # revoke_all_user_tokens
    user = UserFactory()
    rt1 = RefreshTokenFactory(user=user, token="t1")
    rt2 = RefreshTokenFactory(user=user, token="t2")
    assert session_queries.revoke_all_user_tokens(user) == 2
    rt1.refresh_from_db()
    rt2.refresh_from_db()
    assert rt1.is_revoked is True
    assert rt2.is_revoked is True

    # delete_expired_tokens
    rt_expired = RefreshTokenFactory(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    assert session_queries.delete_expired_tokens() == 1
