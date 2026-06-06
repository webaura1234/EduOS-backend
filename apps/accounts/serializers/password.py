"""
Password serializers — forced change and OTP reset.
"""

from rest_framework import serializers

from apps.accounts.validators import validate_password_strength


class ForceChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
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


class OTPRequestSerializer(serializers.Serializer):
    phone = serializers.CharField()
    tenant_id = serializers.UUIDField()
    # Required only when the phone matches multiple accounts (EC-AUTH-12 / 20).
    account_id = serializers.UUIDField(required=False, allow_null=True)


class ResetAccountsSerializer(serializers.Serializer):
    """List the accounts on a phone for the reset account-picker (EC-AUTH-12 / 20)."""
    phone = serializers.CharField()
    tenant_id = serializers.UUIDField()


class AdminResetPasswordSerializer(serializers.Serializer):
    """Admin sets a temporary password for a user (EC-AUTH-21)."""
    # If omitted, the server generates and returns a temp password.
    temp_password = serializers.CharField(
        required=False, allow_blank=True, write_only=True, style={"input_type": "password"}
    )


class OTPVerifySerializer(serializers.Serializer):
    phone = serializers.CharField()
    otp = serializers.CharField(min_length=6, max_length=6)
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    confirm_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    tenant_id = serializers.UUIDField()

    def validate_new_password(self, value):
        validate_password_strength(value)
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return attrs
