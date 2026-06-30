"""Platform-owner student subscription roster — list + mark paid/unpaid."""

from django.utils import timezone
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsPlatformOwner
from apps.organizations.enums import StudentPlatformSubscriptionStatus
from apps.organizations.queries import student_platform_subscription as q
from apps.organizations.serializers.student_platform_subscription import subscription_row_dict


class PlatformStudentSubscriptionListView(APIView):
    """GET /api/v1/organizations/platform/student-subscriptions/"""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        p = request.query_params
        skip_meta = p.get("skipMeta") in ("1", "true")
        tenant_id = p.get("tenantId")
        result = q.list_student_subscriptions(
            tenant_id=tenant_id,
            branch_id=p.get("branchId"),
            plan=p.get("plan", "all"),
            status=p.get("status", "all"),
            q=p.get("q"),
            page=p.get("page", 1),
            page_size=p.get("pageSize", 50),
            skip_meta=skip_meta,
        )
        # skip_meta=True: page-only change — omit filter_options (2 queries saved).
        # Frontend keeps filter_options from the previous full response.
        filter_options = (
            {"tenants": [], "branches": []}
            if skip_meta
            else q.filter_options(tenant_id=tenant_id)
        )
        return Response({
            "rows": [subscription_row_dict(r) for r in result["rows"]],
            "pagination": result["pagination"],
            "filterOptions": filter_options,
            "stats": result["stats"],
        })


class PlatformStudentSubscriptionActionsView(APIView):
    """PATCH /api/v1/organizations/platform/student-subscriptions/actions/"""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def patch(self, request) -> Response:
        sub_id = request.data.get("studentSubscriptionId")
        action = request.data.get("action")
        if not sub_id or action not in {"mark_paid", "mark_unpaid"}:
            return Response(
                {"error": "studentSubscriptionId and action (mark_paid|mark_unpaid) are required."},
                status=http.HTTP_400_BAD_REQUEST,
            )

        row = q.get_subscription_for_action(sub_id)
        if row is None:
            return Response({"error": "Subscription not found."}, status=http.HTTP_404_NOT_FOUND)

        if action == "mark_paid":
            row.status = StudentPlatformSubscriptionStatus.PAID
            row.paid_at = timezone.now()
        else:
            row.status = StudentPlatformSubscriptionStatus.UNPAID
            row.paid_at = None
        row.save(update_fields=["status", "paid_at", "updated_at"])

        return Response({"row": subscription_row_dict(row)})
