"""
Platform-owner operational views.

GET  /platform/audit/                    → PlatformAuditData
GET  /platform/trials/                   → PlatformTrialsData
POST /platform/trials/actions/           → run_pipeline | extend_trial | convert_to_paid
GET  /platform/tickets/                  → PlatformTicketsData
PATCH /platform/tickets/actions/         → set_status | add_internal_note
GET  /platform/support/                  → PlatformSupportModeData
POST /platform/support/                  → enter support mode
DELETE /platform/support/                → exit support mode
GET  /platform/settings/                 → PlatformSettingsData
PATCH /platform/settings/               → toggle announcement | update plan definition
POST /platform/settings/announcements/  → publish announcement
GET  /platform/plan-features/            → PlatformPlanFeatureMatrixData
PATCH /platform/plan-features/           → update feature matrix
GET  /platform/maintenance/              → PlatformMaintenanceMode
PATCH /platform/maintenance/             → update maintenance mode
GET  /platform/integrations/health/      → PlatformIntegrationHealthData
"""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsPlatformOwner
from apps.organizations.queries import platform_ops as ops


class PlatformAuditView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        return Response(ops.get_audit_logs())


class PlatformTrialsView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        return Response(ops.get_trials())


class PlatformTrialActionsView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def post(self, request) -> Response:
        action = request.data.get("action")
        tenant_id = request.data.get("tenantId")

        if action == "run_pipeline":
            pipeline = ops.run_trial_pipeline(user=request.user)
            trials = ops.get_trials()
            msg = (
                f"Pipeline complete: {pipeline['deactivated']} tenant(s) deactivated."
                if pipeline["deactivated"] > 0
                else f"Pipeline complete: {pipeline['movedToGrace']} tenant(s) entered grace."
                if pipeline["movedToGrace"] > 0
                else "Pipeline ran; no status changes required."
            )
            return Response({"message": msg, "pipeline": pipeline, "trials": trials})

        if not tenant_id:
            return Response(
                {"error": "tenantId is required for this action"},
                status=http.HTTP_400_BAD_REQUEST,
            )

        try:
            if action == "extend_trial":
                extend_days = int(request.data.get("extendDays", 14))
                ops.extend_trial(
                    tenant_id=tenant_id,
                    extend_days=extend_days,
                    user=request.user,
                )
                trials = ops.get_trials()
                return Response({"message": f"Trial extended by {extend_days} days.", "trials": trials})

            if action == "convert_to_paid":
                ops.convert_to_paid(tenant_id=tenant_id, user=request.user)
                trials = ops.get_trials()
                return Response({"message": "Tenant converted to paid plan.", "trials": trials})

            return Response({"error": "Unknown action"}, status=http.HTTP_400_BAD_REQUEST)

        except ValueError as exc:
            return Response({"error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)


class PlatformTicketsView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        return Response(ops.list_tickets())


class PlatformTicketActionsView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def patch(self, request) -> Response:
        tenant_subdomain = request.data.get("tenantSubdomain")
        ticket_id = request.data.get("ticketId")
        action = request.data.get("action")

        if not tenant_subdomain or not ticket_id or not action:
            return Response(
                {"error": "tenantSubdomain, ticketId, and action are required"},
                status=http.HTTP_400_BAD_REQUEST,
            )

        try:
            if action == "set_status":
                status_val = request.data.get("status")
                if not status_val:
                    return Response(
                        {"error": "status is required"},
                        status=http.HTTP_400_BAD_REQUEST,
                    )
                ticket = ops.set_ticket_status(
                    tenant_subdomain=tenant_subdomain,
                    ticket_id=ticket_id,
                    status=status_val,
                    user=request.user,
                )
                return Response({"ticket": ticket})

            if action == "add_internal_note":
                message = request.data.get("message", "").strip()
                ticket = ops.add_ticket_platform_note(
                    tenant_subdomain=tenant_subdomain,
                    ticket_id=ticket_id,
                    message=message,
                    user=request.user,
                )
                return Response({"ticket": ticket})

            return Response({"error": "Unknown action"}, status=http.HTTP_400_BAD_REQUEST)

        except ValueError as exc:
            return Response({"error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)


class PlatformSupportView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        return Response(ops.get_support_mode(user=request.user))

    def post(self, request) -> Response:
        tenant_id = request.data.get("tenantId")
        read_only = bool(request.data.get("readOnly", True))
        if not tenant_id:
            return Response(
                {"error": "tenantId is required"},
                status=http.HTTP_400_BAD_REQUEST,
            )
        try:
            result = ops.enter_support_mode(
                tenant_id=tenant_id,
                read_only=read_only,
                user=request.user,
            )
            return Response(result)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)

    def delete(self, request) -> Response:
        result = ops.exit_support_mode(user=request.user)
        return Response(result)


class PlatformSettingsView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        return Response(ops.get_settings())

    def patch(self, request) -> Response:
        body = request.data
        try:
            # Dispatch by body shape (matches the Next.js route)
            if body.get("type") == "announcement_toggle":
                ann_id = body.get("id")
                is_active = bool(body.get("isActive", False))
                ann = ops.set_announcement_active(ann_id, is_active, user=request.user)
                return Response({"announcement": ann})

            # Otherwise treat as UpdatePlatformPlanDefinitionInput
            plan = body.get("plan")
            if not plan:
                return Response(
                    {"error": "plan is required"},
                    status=http.HTTP_400_BAD_REQUEST,
                )
            result = ops.update_plan_definition(
                plan=plan,
                label=body.get("label"),
                max_branches=body.get("maxBranches"),
                max_students=body.get("maxStudents"),
                included_features=body.get("includedFeatures"),
                description=body.get("description"),
                user=request.user,
            )
            return Response({"plan": result})
        except ValueError as exc:
            return Response({"error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)

    def post(self, request) -> Response:
        title = request.data.get("title", "").strip()
        body = request.data.get("body", "").strip()
        severity = request.data.get("severity", "info")
        try:
            ann = ops.publish_announcement(
                title=title,
                body=body,
                severity=severity,
                user=request.user,
            )
            return Response({"announcement": ann}, status=http.HTTP_201_CREATED)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)


class PlatformPlanFeaturesView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        return Response(ops.get_plan_feature_matrix())

    def patch(self, request) -> Response:
        plan = request.data.get("plan")
        flags = request.data.get("flags")
        if not plan or not flags:
            return Response(
                {"error": "plan and flags are required"},
                status=http.HTTP_400_BAD_REQUEST,
            )
        try:
            result = ops.update_plan_feature_matrix(
                plan=plan,
                flags=flags,
                user=request.user,
            )
            return Response(result)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)


class PlatformMaintenanceView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        return Response({"maintenance": ops.get_maintenance()})

    def patch(self, request) -> Response:
        body = request.data
        enabled = bool(body.get("enabled", False))
        try:
            result = ops.update_maintenance(
                enabled=enabled,
                message=body.get("message"),
                block_writes=body.get("blockWrites"),
                scheduled_end_at=body.get("scheduledEndAt"),
                user=request.user,
            )
            return Response({"maintenance": result})
        except Exception as exc:
            return Response({"error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)


class PlatformIntegrationHealthView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        return Response(ops.get_integration_health())
