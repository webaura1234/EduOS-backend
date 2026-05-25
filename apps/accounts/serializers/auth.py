"""
Auth serializers — login, refresh, logout, me.
"""

from rest_framework import serializers

from apps.accounts.models.user import Role


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(
        help_text="Phone number (admin/parent) or Employee ID / Roll Number (faculty/student)."
    )
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    role = serializers.ChoiceField(choices=Role.choices)
    tenant_id = serializers.UUIDField()


class TokenPairSerializer(serializers.Serializer):
    """Shared response shape for any endpoint that returns an access + refresh pair."""
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    must_change_password = serializers.BooleanField(read_only=True, default=False)
    user_id = serializers.UUIDField(read_only=True)
    role = serializers.CharField(read_only=True)


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class MeSerializer(serializers.Serializer):
    """Read-only current user info."""
    id = serializers.UUIDField(read_only=True)
    role = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    email = serializers.EmailField(read_only=True, allow_null=True)
    phone = serializers.CharField(read_only=True, allow_null=True)
    tenant_id = serializers.UUIDField(read_only=True, allow_null=True)
    branch_id = serializers.UUIDField(read_only=True, allow_null=True)
    must_change_password = serializers.BooleanField(read_only=True)
    date_joined = serializers.DateTimeField(read_only=True)
