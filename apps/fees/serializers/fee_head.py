"""Fee head serializers."""

from rest_framework import serializers

from apps.fees.models import FeeHead


class FeeHeadSerializer(serializers.ModelSerializer):
    chargeType = serializers.CharField(source="charge_type")
    billingType = serializers.CharField(source="billing_type")
    refundType = serializers.CharField(source="refund_type")
    isActive = serializers.BooleanField(source="is_active")

    class Meta:
        model = FeeHead
        fields = ["id", "name", "kind", "chargeType", "billingType", "refundType", "isActive"]
        read_only_fields = ["id"]

    def to_internal_value(self, data):
        mapped = dict(data)
        if "chargeType" in mapped:
            mapped["charge_type"] = mapped.pop("chargeType")
        if "billingType" in mapped:
            mapped["billing_type"] = mapped.pop("billingType")
        if "refundType" in mapped:
            mapped["refund_type"] = mapped.pop("refundType")
        if "isActive" in mapped:
            mapped["is_active"] = mapped.pop("isActive")
        return super().to_internal_value(mapped)
