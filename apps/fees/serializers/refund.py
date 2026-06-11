"""Refund serializers."""

from rest_framework import serializers

from apps.fees.models import Refund


class RefundSerializer(serializers.ModelSerializer):
    payment = serializers.UUIDField(source="payment_id")
    amountPaise = serializers.IntegerField(source="amount_paise")
    razorpayRefundId = serializers.CharField(source="razorpay_refund_id", read_only=True)
    idempotencyKey = serializers.CharField(source="idempotency_key")
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Refund
        fields = [
            "id",
            "payment",
            "amountPaise",
            "reason",
            "status",
            "razorpayRefundId",
            "idempotencyKey",
            "createdAt",
        ]
        read_only_fields = ["id", "status", "razorpayRefundId", "createdAt"]
