"""Admin Payments screen — the paginated/filterable counterpart to the
``payments`` field that used to live on AdminFeesOverviewView (unbounded).

Both endpoints take the same filters (``date_from``, ``date_to``, ``status``,
``studentId``, ``search``) so the frontend can request a page of rows and its
matching summary stats with one consistent query-string.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.core.pagination import paginate_queryset
from apps.fees.helpers.payment_dict import payment_dict
from apps.fees.queries import payment as pay_q


def _filters(request) -> dict:
    return dict(
        date_from=request.query_params.get("date_from") or None,
        date_to=request.query_params.get("date_to") or None,
        status=request.query_params.get("status") or None,
        student_id=request.query_params.get("studentId") or None,
        search=request.query_params.get("search") or None,
    )


class AdminPaymentsListView(APIView):
    """GET -> {count, next, previous, results: FeePayment[]} — paginated, filtered."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        filters = _filters(request)
        qs = pay_q.list_payments_for_branch_filtered(branch.pk, **filters)
        return Response(paginate_queryset(request, qs, payment_dict))


class AdminPaymentsSummaryView(APIView):
    """GET -> {count, totalPaise, methodBreakdown} for the same filters as
    AdminPaymentsListView, computed via DB aggregation (not a Python loop over
    potentially unbounded matching rows)."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        filters = _filters(request)
        filters.pop("search", None)  # summary doesn't need free-text search
        return Response(pay_q.payment_summary_for_branch(branch.pk, **filters))
