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


class DisambiguateLoginSerializer(serializers.Serializer):
    """Universal login input without a role — backend resolves it (EC-AUTH-11)."""
    identifier = serializers.CharField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
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


class SwitchLinkedSerializer(serializers.Serializer):
    """Switch to a linked account (same person, multi-role) — re-verifies password."""
    target_user_id = serializers.UUIDField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class PlatformLoginSerializer(serializers.Serializer):
    """Platform-owner login — phone identifier + password, no tenant."""
    identifier = serializers.CharField(help_text="Platform owner phone number.")
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class BranchAdminSerializer(serializers.Serializer):
    """Branch-admin row for the super-admin admin-management screen."""
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(source="full_name", read_only=True)
    phone = serializers.CharField(read_only=True, allow_null=True)
    branchId = serializers.UUIDField(source="branch_id", read_only=True, allow_null=True)
    branchName = serializers.SerializerMethodField()
    isActive = serializers.BooleanField(source="is_active", read_only=True)
    lastLoginAt = serializers.DateTimeField(source="last_login", read_only=True, allow_null=True)

    def get_branchName(self, obj):
        return obj.branch.name if obj.branch_id else ""


class InviteAdminSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=20)
    branchId = serializers.UUIDField()


class UpdateAdminSerializer(serializers.Serializer):
    isActive = serializers.BooleanField(required=False)
    branchId = serializers.UUIDField(required=False)


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
