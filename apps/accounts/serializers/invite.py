"""
Invite serializers — create invite (admin) and accept invite (new user).
"""

from rest_framework import serializers

from apps.accounts.models.user import Role
from apps.accounts.validators import validate_password_strength

INVITABLE_ROLES = [Role.FACULTY, Role.STUDENT, Role.PARENT, Role.ADMIN]


class CreateInviteSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=[(r, r) for r in INVITABLE_ROLES])
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100, required=False, default="")
    phone = serializers.CharField(required=False, allow_blank=True, default=None)
    custom_login_id = serializers.CharField(required=False, allow_blank=True, default=None)
    email = serializers.EmailField(required=False, allow_null=True, default=None)
    branch_id = serializers.UUIDField(required=False, allow_null=True, default=None)


class CreateInviteResponseSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(read_only=True)
    invite_token = serializers.UUIDField(read_only=True)


class AcceptInviteSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    confirm_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_new_password(self, value):
        validate_password_strength(value)
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return attrs
