"""
Platform-owner plan management views.

GET  /api/v1/organizations/platform/plans/
    Returns the static plan catalog and the current plan for every tenant.

PATCH /api/v1/organizations/platform/plans/
    Changes the plan for a specific tenant.
    Returns 409 with limitBlocked payload when usage exceeds the new plan limits.

POST /api/v1/organizations/platform/plan-limits/validate/
    Validates whether a plan change would violate usage limits.
    Returns 200 {"ok": true} or 409 with limitBlocked payload.
"""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsPlatformOwner
from apps.organizations.queries import platform_tenant as q


class PlatformPlanView(APIView):
    """
    GET  → {catalog, tenants}
    PATCH → PlatformChangePlanResult (or 409 on limit violation)
    """
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        return Response({
            "catalog": q.plan_catalog(),
            "tenants": q.plan_rows(),
        })

    def patch(self, request) -> Response:
        tenant_id = request.data.get("tenantId")
        new_plan = request.data.get("newPlan")

        if not tenant_id or not new_plan:
            return Response(
                {"error": "tenantId and newPlan are required."},
                status=http.HTTP_400_BAD_REQUEST,
            )
        if new_plan not in q.PLAN_LIMITS:
            return Response(
                {"error": f"Invalid plan '{new_plan}'."},
                status=http.HTTP_400_BAD_REQUEST,
            )

        try:
            result = q.change_plan(tenant_id, new_plan, user=request.user)
        except q._PlanLimitViolation as exc:
            return Response(exc.payload, status=http.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)

        return Response(result)


class PlatformPlanLimitsValidateView(APIView):
    """
    POST → {"ok": true} or 409 with PlatformPlanLimitBlockedResponse
    """
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def post(self, request) -> Response:
        tenant_id = request.data.get("tenantId")
        new_plan = request.data.get("newPlan")
        context = request.data.get("context", "plan_downgrade")

        if context != "plan_downgrade" or not tenant_id or not new_plan:
            return Response({"ok": True})

        if new_plan not in q.PLAN_LIMITS:
            return Response({"ok": True})

        blocked = q.validate_plan_limits(tenant_id, new_plan)
        if blocked:
            return Response(blocked, status=http.HTTP_409_CONFLICT)

        return Response({"ok": True})
