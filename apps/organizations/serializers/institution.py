"""
Institution-settings serializers (super-admin settings screen).

Mirrors @eduos/types `TenantInstitutionSettings` / `UpdateTenantInstitutionSettingsInput`.
"""

from rest_framework import serializers


class AddressInputSerializer(serializers.Serializer):
    line1 = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    line2 = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    city = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    state = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    pincode = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")


class UpdateInstitutionSettingsSerializer(serializers.Serializer):
    institutionName = serializers.CharField(max_length=255, required=False)
    institutionType = serializers.ChoiceField(choices=["school", "college"], required=False)
    logoUrl = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    address = AddressInputSerializer(required=False)
    parentPortalEnabled = serializers.BooleanField(required=False)


class GoLiveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["go_live", "undo_go_live"])


def institution_settings_dict(tenant) -> dict:
    """Present a Tenant as the camelCase settings payload the frontend expects."""
    return {
        "institutionName": tenant.name,
        "institutionType": tenant.institution_type,
        "logoUrl": tenant.logo_s3_key or None,
        "address": {
            "line1": tenant.address_line1,
            "line2": tenant.address_line2,
            "city": tenant.city,
            "state": tenant.state,
            "pincode": tenant.postal_code,
        },
        "goLiveAt": tenant.activated_at.isoformat() if tenant.activated_at else None,
        "parentPortalEnabled": tenant.parent_access_enabled,
    }
