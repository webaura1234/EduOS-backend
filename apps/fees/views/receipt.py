"""Receipt views — download presigned URL for a receipt PDF."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status as http

from apps.accounts.models.user import Role
from apps.fees.queries.receipt import get_receipt
from apps.integrations.adapters.s3 import get_s3_adapter


class ReceiptDownloadView(APIView):
    """GET → presigned S3 URL for a receipt PDF.

    Students can download their own receipts; admins can download any receipt in their branch.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, receipt_id):
        user = request.user

        if user.role in (Role.ADMIN, Role.SUPER_ADMIN):
            branch_id = getattr(user, "branch_id", None)
            receipt = get_receipt(branch_id, receipt_id)
        elif user.role == Role.STUDENT:
            # Fetch without branch restriction but verify ownership below.
            try:
                from apps.fees.models import Receipt
                receipt = Receipt.objects.select_related(
                    "payment__invoice__student__student_profile"
                ).get(pk=receipt_id, is_active=True)
                # Ownership check: the invoice's student profile must belong to this user.
                student_user_id = receipt.payment.invoice.student.user_id
                if student_user_id != user.pk:
                    receipt = None
            except Exception:  # noqa: BLE001
                receipt = None
        else:
            return Response({"error": "Not authorised."}, status=http.HTTP_403_FORBIDDEN)

        if not receipt:
            return Response({"error": "Receipt not found."}, status=http.HTTP_404_NOT_FOUND)

        if not receipt.pdf_s3_key:
            return Response({"error": "PDF not yet generated for this receipt."},
                            status=http.HTTP_404_NOT_FOUND)

        s3 = get_s3_adapter()
        url = s3.signed_url(key=receipt.pdf_s3_key, ttl_seconds=604800)  # 7 days
        return Response({"downloadUrl": url, "receiptNo": receipt.receipt_no})
