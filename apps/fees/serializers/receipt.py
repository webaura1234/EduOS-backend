"""Receipt serializers."""

from rest_framework import serializers

from apps.fees.models import Receipt


class ReceiptSerializer(serializers.ModelSerializer):
    payment = serializers.UUIDField(source="payment_id", read_only=True)
    sequenceNumber = serializers.IntegerField(source="sequence_number", read_only=True)
    financialYear = serializers.CharField(source="financial_year", read_only=True)
    pdfS3Key = serializers.CharField(source="pdf_s3_key", read_only=True)
    issuedAt = serializers.DateTimeField(source="issued_at", read_only=True)
    receiptNo = serializers.CharField(source="receipt_no", read_only=True)

    class Meta:
        model = Receipt
        fields = [
            "id",
            "payment",
            "sequenceNumber",
            "financialYear",
            "pdfS3Key",
            "issuedAt",
            "receiptNo",
        ]
        read_only_fields = fields
