"""Views — audit log read + chain verification (admin/super_admin)."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.analytics.interactors import audit as audit_i
from apps.analytics.queries import audit as audit_q
from apps.analytics.serializers.audit import AuditLogSerializer


class AuditLogListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        rows = audit_q.list_audit(
            request.user.tenant_id,
            action=request.query_params.get("action"),
            limit=int(request.query_params.get("limit", 50)),
        )
        return Response({"audit": AuditLogSerializer(rows, many=True).data})


class AuditVerifyView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        return Response(audit_i.verify_chain(request.user.tenant_id))
