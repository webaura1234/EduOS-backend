"""Tab-scoped admin fees GET endpoints."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import AcademicYear
from apps.academics.queries.structure import list_batches
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.fees.queries import concession as conc_q
from apps.fees.queries import refund as ref_q
from apps.fees.queries import structure as struct_q
from apps.fees.views.admin_overview import (
    _concession_request,
    _concession_rule,
    _credit_note,
    _installment_schedules,
    _ledger_and_collection,
    _reconciliation_list,
    _refund,
    _structure,
    _webhook,
)


def _fees_meta(branch):
    academic_years = list(
        AcademicYear.objects.filter(branch_id=branch.pk, is_active=True).order_by("-start_date")
    )
    current_ay = next((y for y in academic_years if y.is_current), academic_years[0] if academic_years else None)
    from apps.fees.helpers.payment_dict import batch_label as _batch_label

    return {
        "institutionType": branch.tenant.institution_type,
        "batches": [{"id": str(b.id), "label": _batch_label(b)} for b in list_batches(branch.pk)],
        "currentAcademicYearId": str(current_ay.id) if current_ay else None,
    }


class AdminFeesStructureTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response({
            **_fees_meta(branch),
            "structures": [_structure(s) for s in struct_q.list_structures(branch.pk)],
        })


class AdminFeesConcessionsTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response({
            **_fees_meta(branch),
            "concessionRules": [_concession_rule(r) for r in conc_q.list_concession_rules(branch.pk)],
            "concessionRequests": [
                _concession_request(r) for r in conc_q.list_concession_requests(branch.pk)
            ],
        })


class AdminFeesCollectionsTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        ledger, collection = _ledger_and_collection(branch)
        return Response({**_fees_meta(branch), "ledger": ledger, "collection": collection})


class AdminFeesDefaultersTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        ledger, collection = _ledger_and_collection(branch)
        overdue = [row for row in ledger if row.get("isOverdue")]
        return Response({
            **_fees_meta(branch),
            "ledger": overdue,
            "collection": collection,
        })


class AdminFeesInstallmentsTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response({
            **_fees_meta(branch),
            "installmentSchedulesByStudent": _installment_schedules(branch),
        })


class AdminFeesReconciliationTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response({
            **_fees_meta(branch),
            "reconciliation": _reconciliation_list(branch),
            "webhooks": [_webhook(w) for w in conc_q.list_webhooks()],
        })


class AdminFeesRefundsTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response({
            **_fees_meta(branch),
            "refunds": [_refund(r) for r in ref_q.list_refunds(branch.pk)],
        })


class AdminFeesScholarshipsTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response({
            **_fees_meta(branch),
            "creditNotes": [_credit_note(c) for c in conc_q.list_credit_notes(branch.pk)],
        })


class AdminFeesInvoicesTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response({
            **_fees_meta(branch),
            "creditNoteRequests": [],
            "examFeeInvoices": [],
        })
