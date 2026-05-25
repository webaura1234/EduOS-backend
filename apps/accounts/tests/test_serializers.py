import pytest
from rest_framework import serializers

from apps.accounts.serializers.auth import LoginSerializer, RefreshSerializer, MeSerializer
from apps.accounts.serializers.password import ForceChangePasswordSerializer, OTPRequestSerializer, OTPVerifySerializer
from apps.accounts.serializers.invite import CreateInviteSerializer, AcceptInviteSerializer
from apps.accounts.models.user import Role


def test_login_serializer_validation():
    # Valid data
    data = {
        "identifier": "EMP123",
        "password": "TestPassword123!",
        "role": Role.FACULTY,
        "tenant_id": "11111111-2222-3333-4444-555555555555",
    }
    serializer = LoginSerializer(data=data)
    assert serializer.is_valid() is True

    # Missing field
    data_invalid = {
        "identifier": "EMP123",
        "password": "TestPassword123!",
        "role": Role.FACULTY,
    }
    serializer_invalid = LoginSerializer(data=data_invalid)
    assert serializer_invalid.is_valid() is False
    assert "tenant_id" in serializer_invalid.errors


def test_force_change_password_serializer():
    # Passwords match and strong
    data = {
        "current_password": "OldPass123!",
        "new_password": "NewSecurePass321!",
        "confirm_password": "NewSecurePass321!",
    }
    serializer = ForceChangePasswordSerializer(data=data)
    assert serializer.is_valid() is True

    # Passwords do not match
    data_mismatch = {
        "current_password": "OldPass123!",
        "new_password": "NewSecurePass321!",
        "confirm_password": "DifferentPass123!",
    }
    serializer_mismatch = ForceChangePasswordSerializer(data=data_mismatch)
    assert serializer_mismatch.is_valid() is False
    assert "confirm_password" in serializer_mismatch.errors

    # Weak password
    data_weak = {
        "current_password": "OldPass123!",
        "new_password": "weak",
        "confirm_password": "weak",
    }
    serializer_weak = ForceChangePasswordSerializer(data=data_weak)
    assert serializer_weak.is_valid() is False
    assert "new_password" in serializer_weak.errors


def test_otp_request_serializer():
    data = {
        "phone": "+919876543210",
        "tenant_id": "11111111-2222-3333-4444-555555555555",
    }
    serializer = OTPRequestSerializer(data=data)
    assert serializer.is_valid() is True


def test_otp_verify_serializer():
    data = {
        "phone": "+919876543210",
        "otp": "123456",
        "new_password": "NewSecurePass321!",
        "confirm_password": "NewSecurePass321!",
        "tenant_id": "11111111-2222-3333-4444-555555555555",
    }
    serializer = OTPVerifySerializer(data=data)
    assert serializer.is_valid() is True


def test_create_invite_serializer():
    data = {
        "role": Role.STUDENT,
        "first_name": "Ramesh",
        "custom_login_id": "STU123",
    }
    serializer = CreateInviteSerializer(data=data)
    assert serializer.is_valid() is True


def test_accept_invite_serializer():
    data = {
        "token": "11111111-2222-3333-4444-555555555555",
        "new_password": "NewSecurePass321!",
        "confirm_password": "NewSecurePass321!",
    }
    serializer = AcceptInviteSerializer(data=data)
    assert serializer.is_valid() is True
