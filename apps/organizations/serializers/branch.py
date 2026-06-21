"""
Branch serializers.

Output shapes use the camelCase keys the frontend `SuperAdminBranch` type expects.
"""

from rest_framework import serializers


class BranchSerializer(serializers.Serializer):
    """Output shape — matches @eduos/types `SuperAdminBranch`."""
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    city = serializers.CharField(read_only=True)
    isActive = serializers.BooleanField(source="is_active", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, read_only=True, allow_null=True,
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, read_only=True, allow_null=True,
    )
    geofenceRadiusM = serializers.IntegerField(
        source="geofence_radius_m", read_only=True, allow_null=True,
    )
    # Resolved branding (branch override → tenant fallback) for white-labeled clients.
    theme = serializers.SerializerMethodField()

    def get_theme(self, obj) -> dict:
        from apps.organizations.branding import branch_theme
        return branch_theme(obj)


class CreateBranchSerializer(serializers.Serializer):
    """Input — matches `SuperAdminCreateBranchInput`."""
    name = serializers.CharField(max_length=255)
    code = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    city = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class SetBranchActiveSerializer(serializers.Serializer):
    """Input for PATCH /branches/actions."""
    action = serializers.ChoiceField(choices=["set_active"])
    branchId = serializers.UUIDField()
    isActive = serializers.BooleanField()


class UpdateBranchSettingsSerializer(serializers.Serializer):
    """Input for PATCH /branches/<id>/settings/ — geo-fence config (F-103)."""
    latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True,
    )
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True,
    )
    geofenceRadiusM = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    def validate(self, attrs):
        lat = attrs.get("latitude")
        lng = attrs.get("longitude")
        radius = attrs.get("geofenceRadiusM")

        if lat is not None and not (-90 <= lat <= 90):
            raise serializers.ValidationError({"latitude": "Must be between -90 and 90."})
        if lng is not None and not (-180 <= lng <= 180):
            raise serializers.ValidationError({"longitude": "Must be between -180 and 180."})

        # Enabling geo-fence requires all three values.
        if radius is not None:
            if lat is None or lng is None:
                raise serializers.ValidationError(
                    "latitude and longitude are required when geofenceRadiusM is set.",
                )

        # Partial lat/lng without radius is allowed (in-progress config), but both must be set together.
        if (lat is None) ^ (lng is None):
            raise serializers.ValidationError(
                "latitude and longitude must both be set or both be cleared.",
            )

        return attrs
