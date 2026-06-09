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
