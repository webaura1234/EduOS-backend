"""Payment serializers."""

from rest_framework import serializers

from apps.fees.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    invoice = serializers.UUIDField(source="invoice_id")
    amountPaise = serializers.IntegerField(source="amount_paise")
    razorpayOrderId = serializers.CharField(source="razorpay_order_id", read_only=True)
    razorpayPaymentId = serializers.CharField(source="razorpay_payment_id", read_only=True)
    capturedAt = serializers.DateTimeField(source="captured_at", read_only=True)
    idempotencyKey = serializers.CharField(source="idempotency_key")
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice",
            "amountPaise",
            "method",
            "status",
            "razorpayOrderId",
            "razorpayPaymentId",
            "capturedAt",
            "idempotencyKey",
            "createdAt",
        ]
        read_only_fields = ["id", "status", "razorpayOrderId", "razorpayPaymentId", "capturedAt", "createdAt"]
