"""Admin: record an offline payment against a student (allocates to oldest open invoice)."""

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.models.profile import StudentProfile
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.fees.interactors.payment import RecordOfflinePaymentInteractor
from apps.fees.queries.invoice import list_dues_for_student

# FE method → backend PaymentMethod (offline only; cash stays cash, rest = bank transfer).
_METHOD = {"cash": "cash", "cheque": "cheque", "upi": "bank_transfer",
           "card": "bank_transfer", "netbanking": "bank_transfer"}


class AdminRecordPaymentByStudentView(APIView):
    """POST { studentId, amountPaise, method, referenceNo? } → record offline payment
    allocated to the student's oldest invoice that still has a balance."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        resolve_branch(request)  # tenant/branch guard
        student_id = request.data.get("studentId")
        amount_paise = request.data.get("amountPaise")
        method = _METHOD.get(request.data.get("method"), "cash")

        if not student_id or not amount_paise:
            raise ValidationError("studentId and amountPaise are required.")

        profile = (
            StudentProfile.objects.select_related("user")
            .filter(pk=student_id, is_active=True)
            .first()
        )
        if profile is None:
            raise ValidationError({"studentId": "Student profile not found."})

        enrollment = get_active_enrollment_for_profile(profile.id)
        if enrollment is None:
            raise ValidationError({"studentId": "No active enrollment for this student."})

        invoice = next(
            (inv for inv in list_dues_for_student(enrollment.id) if inv.balance_paise > 0),
            None,
        )
        if invoice is None:
            raise ValidationError("This student has no open dues to apply a payment to.")

        payment = RecordOfflinePaymentInteractor(
            invoice_id=invoice.id, amount_paise=int(amount_paise), method=method,
            payer_user=profile.user, reference_no=request.data.get("referenceNo"),
            user=request.user,
        ).execute()

        return Response(
            {"id": str(payment.id), "invoiceId": str(invoice.id),
             "amountPaise": payment.amount_paise},
            status=status.HTTP_201_CREATED,
        )
