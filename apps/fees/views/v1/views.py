"""DRF Views for Fees and Payments."""

import json
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminOrSuperAdmin, IsParent, IsStudent
from apps.fees.enums import ConcessionStatus, CreditNoteStatus, InvoiceStatus, PaymentMethod, RefundStatus
from apps.fees.serializers import (
    ConcessionRequestSerializer,
    ConcessionRuleSerializer,
    CreditNoteSerializer,
    FeeInvoiceSerializer,
    FeeStructureSerializer,
    PaymentSerializer,
    ReceiptSerializer,
    RefundSerializer,
    StudentFeeAssignmentSerializer,
)
from apps.fees.interactors import (
    ApproveConcessionRequestInteractor,
    ApproveCreditNoteInteractor,
    ApproveRefundInteractor,
    CreateConcessionRequestInteractor,
    CreateConcessionRuleInteractor,
    CreateCreditNoteInteractor,
    CreatePaymentOrderInteractor,
    GetCollectionDashboardInteractor,
    RecordOfflinePaymentInteractor,
    ReconcilePendingPaymentInteractor,
    RequestRefundInteractor,
    VerifyPaymentCaptureInteractor,
    create_fee_structure,
    generate_invoices_for_batch,
    update_fee_structure,
)
from apps.fees.queries import (
    get_structure,
    get_student_in_branch,
    get_student_profile,
    list_defaulters,
    list_invoices,
    list_receipts,
)
from apps.fees.queries.concession import (
    list_approved_requests_for_student,
    list_concession_requests,
    list_concession_rules,
    list_credit_notes,
)
from apps.fees.queries.invoice import (
    get_invoice_for_student_user,
    list_dues_for_student,
    list_dues_for_student_user,
)
from apps.fees.queries.portal import guardian_portal_link, list_receipts_for_student
from apps.fees.queries.refund import list_refunds
from apps.fees.queries.structure import list_structures
from apps.fees.queries.webhook import create_webhook_log, get_webhook_log
from apps.organizations.queries.branch import get_branch
from apps.integrations.adapters.payments import get_gateway


def get_request_branch(request):
    """Helper to resolve the Branch for the current request context."""
    branch_id = request.user.branch_id
    if not branch_id:
        branch_id = request.query_params.get("branchId") or request.data.get("branchId")
    if not branch_id:
        raise ValidationError({"branchId": "Branch ID is required."})
    branch = get_branch(request.user.tenant_id, branch_id)
    if not branch:
        raise ValidationError({"branchId": "Invalid Branch ID or access denied."})
    return branch


# ── Fee Structures & Assignments ─────────────────────────────────────────────
class FeeStructureViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    serializer_class = FeeStructureSerializer

    def get_queryset(self):
        branch = get_request_branch(self.request)
        return list_structures(branch.id)

    def perform_create(self, serializer):
        branch = get_request_branch(self.request)
        try:
            create_fee_structure(
                branch_id=branch.id,
                name=serializer.validated_data["name"],
                academic_year_id=serializer.validated_data["academic_year_id"],
                batch_id=serializer.validated_data.get("batch_id"),
                components=serializer.validated_data.get("components", []),
                user=self.request.user,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)

    def perform_update(self, serializer):
        try:
            update_fee_structure(
                structure=self.get_object(),
                name=serializer.validated_data.get("name"),
                components=serializer.validated_data.get("components"),
                user=self.request.user,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)


class StudentFeeAssignmentView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        branch = get_request_branch(request)
        serializer = StudentFeeAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        student_id = serializer.validated_data["student_id"]
        structure_id = serializer.validated_data["fee_structure_id"]

        student = get_student_in_branch(branch.id, student_id)
        if not student:
            raise ValidationError({"student": "Student not found in this branch."})

        structure = get_structure(branch.id, structure_id)
        if not structure:
            raise ValidationError({"feeStructure": "Fee structure not found."})

        from apps.fees.queries.structure import create_assignment, assignment_exists
        if assignment_exists(student.id, structure.id):
            raise ValidationError({"nonFieldErrors": "Assignment already exists for this student and structure."})

        # Fetch concessions via query layer
        approved_concessions = list_approved_requests_for_student(student.id)
        discount_lines = []
        for req in approved_concessions:
            label = req.rule.name if req.rule else "Concession"
            discount_lines.append({
                "request_id": str(req.id),
                "label": label,
                "amount_paise": req.amount_paise,
            })

        assignment = create_assignment(
            student=student,
            fee_structure=structure,
            structure_snapshot=structure.components or [],
            discount_lines=discount_lines,
            user=request.user,
        )

        return Response(StudentFeeAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)


class GenerateInvoicesView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        branch = get_request_branch(request)
        batch_id = request.data.get("batchId")
        structure_id = request.data.get("feeStructureId")
        academic_year_id = request.data.get("academicYearId")

        if not batch_id or not structure_id or not academic_year_id:
            raise ValidationError("batchId, feeStructureId, and academicYearId are required.")

        try:
            from apps.academics.queries.structure import get_batch
            from apps.academics.queries.rollover import get_academic_year
            batch = get_batch(branch.id, batch_id)
            structure = get_structure(branch.id, structure_id)
            ay = get_academic_year(academic_year_id)

            if not batch or not structure or not ay:
                raise ValidationError("Invalid batch, feeStructure, or academicYear ID.")
        except (DjangoValidationError, ValueError, TypeError):
            raise ValidationError("Invalid batch, feeStructure, or academicYear ID.")

        try:
            invoices = generate_invoices_for_batch(
                branch=branch,
                batch_id=batch.id,
                academic_year=ay,
                fee_structure=structure,
                user=request.user,
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)

        return Response(
            {"message": f"Successfully generated {len(invoices)} invoices."},
            status=status.HTTP_201_CREATED,
        )


# ── Concessions & Credit Notes ───────────────────────────────────────────────
class ConcessionRuleViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    serializer_class = ConcessionRuleSerializer

    def get_queryset(self):
        branch = get_request_branch(self.request)
        return list_concession_rules(branch.id)

    def perform_create(self, serializer):
        branch = get_request_branch(self.request)
        try:
            interactor = CreateConcessionRuleInteractor(
                branch=branch,
                name=serializer.validated_data["name"],
                amount_paise=serializer.validated_data.get("amount_paise"),
                percent=serializer.validated_data.get("percent"),
                criteria=serializer.validated_data.get("criteria", {}),
                user=self.request.user,
            )
            interactor.execute()
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)


class ConcessionRequestViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    serializer_class = ConcessionRequestSerializer

    def get_queryset(self):
        branch = get_request_branch(self.request)
        status_param = self.request.query_params.get("status")
        return list_concession_requests(branch.id, status=status_param)

    def perform_create(self, serializer):
        branch = get_request_branch(self.request)
        student_id = serializer.validated_data["student_id"]
        student = get_student_in_branch(branch.id, student_id)
        if not student:
            raise ValidationError({"student": "Student not found in this branch."})

        try:
            interactor = CreateConcessionRequestInteractor(
                branch=branch,
                student=student,
                rule_id=serializer.validated_data.get("rule_id"),
                amount_paise=serializer.validated_data["amount_paise"],
                requested_by=self.request.user,
                note=serializer.initial_data.get("note", ""),
            )
            interactor.execute()
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)

    def partial_update(self, request, *args, **kwargs):
        dec = request.data.get("status")
        if not dec or dec not in [ConcessionStatus.APPROVED, ConcessionStatus.REJECTED]:
            raise ValidationError({"status": "Must approve or reject request."})

        try:
            interactor = ApproveConcessionRequestInteractor(
                request_id=self.get_object().id,
                status=dec,
                approver_user=request.user,
            )
            req = interactor.execute()
            return Response(ConcessionRequestSerializer(req).data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)


class CreditNoteViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    serializer_class = CreditNoteSerializer

    def get_queryset(self):
        branch = get_request_branch(self.request)
        return list_credit_notes(branch.id)

    def perform_create(self, serializer):
        branch = get_request_branch(self.request)
        student_id = serializer.validated_data["student_id"]
        student = get_student_in_branch(branch.id, student_id)
        if not student:
            raise ValidationError({"student": "Student not found in this branch."})

        try:
            interactor = CreateCreditNoteInteractor(
                branch=branch,
                student=student,
                invoice_id=serializer.validated_data["invoice_id"],
                amount_paise=serializer.validated_data["amount_paise"],
                reason=serializer.initial_data.get("reason", ""),
                user=self.request.user,
            )
            interactor.execute()
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)

    def partial_update(self, request, *args, **kwargs):
        dec = request.data.get("status")
        if not dec or dec not in [CreditNoteStatus.APPROVED, CreditNoteStatus.REJECTED]:
            raise ValidationError({"status": "Must approve or reject request."})

        try:
            interactor = ApproveCreditNoteInteractor(
                credit_note_id=self.get_object().id,
                status=dec,
                approver_user=request.user,
            )
            cn = interactor.execute()
            return Response(CreditNoteSerializer(cn).data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)


# ── Dashboards & Defaulters ──────────────────────────────────────────────────
class CollectionDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = get_request_branch(request)
        interactor = GetCollectionDashboardInteractor(branch.id)
        return Response(interactor.execute())


class DefaultersListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = get_request_branch(request)
        invoices = list_defaulters(branch.id)
        return Response(FeeInvoiceSerializer(invoices, many=True).data)


# ── Payments, Checkout, Webhooks ─────────────────────────────────────────────
class CreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        invoice_id = request.data.get("invoiceId")
        amount_paise = request.data.get("amountPaise")
        idempotency_key = request.data.get("idempotencyKey")
        method = request.data.get("method", PaymentMethod.RAZORPAY)

        if not invoice_id or not amount_paise or not idempotency_key:
            raise ValidationError("invoiceId, amountPaise, and idempotencyKey are required.")

        try:
            interactor = CreatePaymentOrderInteractor(
                invoice_id=invoice_id,
                amount_paise=amount_paise,
                method=method,
                payer_user=request.user,
                idempotency_key=idempotency_key,
            )
            payment = interactor.execute()
            return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)


class VerifyPaymentCaptureView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        payment_id = request.data.get("paymentId")
        razorpay_payment_id = request.data.get("razorpayPaymentId")
        razorpay_order_id = request.data.get("razorpayOrderId")
        signature = request.data.get("razorpaySignature")

        if not razorpay_payment_id or not razorpay_order_id or not signature:
            raise ValidationError("razorpayPaymentId, razorpayOrderId, and razorpaySignature are required.")

        try:
            interactor = VerifyPaymentCaptureInteractor(
                payment_id=payment_id,
                razorpay_payment_id=razorpay_payment_id,
                razorpay_order_id=razorpay_order_id,
                signature=signature,
            )
            payment = interactor.execute()
            return Response(PaymentSerializer(payment).data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)


class RecordOfflinePaymentView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        invoice_id = request.data.get("invoiceId")
        amount_paise = request.data.get("amountPaise")
        method = request.data.get("method")
        student_id = request.data.get("studentId")
        reference_no = request.data.get("referenceNo")

        if not invoice_id or not amount_paise or not method or not student_id:
            raise ValidationError("invoiceId, amountPaise, method, and studentId are required.")

        student = get_student_profile(student_id)
        if not student:
            raise ValidationError({"studentId": "Student profile not found."})

        try:
            interactor = RecordOfflinePaymentInteractor(
                invoice_id=invoice_id,
                amount_paise=amount_paise,
                method=method,
                payer_user=student.user,
                reference_no=reference_no,
                user=request.user,
            )
            payment = interactor.execute()
            return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)


class RazorpayWebhookView(APIView):
    """Public webhook receiver for Razorpay events (EC-FEE-01 / EC-FEE-02)."""
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        signature = request.META.get("HTTP_X_RAZORPAY_SIGNATURE")
        if not signature:
            return Response({"detail": "Missing signature."}, status=status.HTTP_400_BAD_REQUEST)

        body_bytes = request.body
        gateway = get_gateway()
        if not gateway.verify_webhook_signature(body_bytes, signature):
            return Response({"detail": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except ValueError:
            return Response({"detail": "Malformed JSON body."}, status=status.HTTP_400_BAD_REQUEST)

        event_id = payload.get("id")
        if not event_id:
            return Response({"detail": "Missing event ID."}, status=status.HTTP_400_BAD_REQUEST)

        # Webhook deduplication (EC-FEE-02)
        if get_webhook_log(event_id):
            return Response({"detail": "Event already processed."}, status=status.HTTP_200_OK)

        event_type = payload.get("event")
        if event_type == "payment.captured":
            payment_data = payload["payload"]["payment"]["entity"]
            rp_payment_id = payment_data["id"]
            rp_order_id = payment_data["order_id"]

            # Process verify idempotently
            try:
                interactor = VerifyPaymentCaptureInteractor(
                    razorpay_payment_id=rp_payment_id,
                    razorpay_order_id=rp_order_id,
                )
                interactor.execute()
            except DjangoValidationError as exc:
                # Log but return 200/400 appropriately
                pass

        # Log event processed
        create_webhook_log(event_id=event_id, payload=payload)

        return Response({"status": "processed"}, status=status.HTTP_200_OK)


# ── Student / Parent Portal ──────────────────────────────────────────────────
class StudentPortalDuesView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        from apps.accounts.models import StudentProfile
        try:
            student = request.user.student_profile
        except StudentProfile.DoesNotExist:
            raise ValidationError("Student profile not found.")

        invoices = list_dues_for_student_user(student.user_id)
        return Response(FeeInvoiceSerializer(invoices, many=True).data)


class StudentPortalReceiptsView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        from apps.accounts.models import StudentProfile
        try:
            student = request.user.student_profile
        except StudentProfile.DoesNotExist:
            raise ValidationError("Student profile not found.")

        receipts = list_receipts_for_student(student.user_id)
        return Response(ReceiptSerializer(receipts, many=True).data)


class ParentPortalChildDuesView(APIView):
    permission_classes = [IsAuthenticated, IsParent]

    def get(self, request, student_id):
        # Verify parent links to student via query layer
        link = guardian_portal_link(request.user.id, student_id)
        if not link:
            raise PermissionDenied("You do not have access to this student's portal.")

        invoices = list_dues_for_student_user(student_id)
        return Response(FeeInvoiceSerializer(invoices, many=True).data)


class ParentPortalChildPayView(APIView):
    permission_classes = [IsAuthenticated, IsParent]

    def post(self, request, student_id):
        # Verify parent links to student via query layer
        link = guardian_portal_link(request.user.id, student_id)
        if not link:
            raise PermissionDenied("You do not have access to this student's portal.")

        invoice_id = request.data.get("invoiceId")
        amount_paise = request.data.get("amountPaise")
        idempotency_key = request.data.get("idempotencyKey")

        if not invoice_id or not amount_paise or not idempotency_key:
            raise ValidationError("invoiceId, amountPaise, and idempotencyKey are required.")

        invoice = get_invoice_for_student_user(invoice_id, student_id)
        if not invoice:
            raise ValidationError("Invoice not found for the given child student.")

        try:
            interactor = CreatePaymentOrderInteractor(
                invoice_id=invoice.id,
                amount_paise=amount_paise,
                method=PaymentMethod.RAZORPAY,
                payer_user=request.user,
                idempotency_key=idempotency_key,
            )
            payment = interactor.execute()
            return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)


# ── Refunds View ─────────────────────────────────────────────────────────────
class RefundViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    serializer_class = RefundSerializer

    def get_queryset(self):
        branch = get_request_branch(self.request)
        status_param = self.request.query_params.get("status")
        return list_refunds(branch.id, status=status_param)

    def perform_create(self, serializer):
        try:
            interactor = RequestRefundInteractor(
                payment_id=serializer.validated_data["payment_id"],
                amount_paise=serializer.validated_data["amount_paise"],
                reason=serializer.initial_data.get("reason", ""),
                user=self.request.user,
            )
            interactor.execute()
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)

    def partial_update(self, request, *args, **kwargs):
        dec = request.data.get("status")
        if not dec or dec != RefundStatus.APPROVED:
            raise ValidationError({"status": "Must set status to approved."})

        try:
            interactor = ApproveRefundInteractor(
                refund_id=self.get_object().id,
                approver_user=request.user,
            )
            refund = interactor.execute()
            return Response(RefundSerializer(refund).data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
