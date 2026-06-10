"""Views — leave apply/queue/review and the audit log."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.attendance.interactors import leave as leave_i
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.attendance.queries import audit as audit_q
from apps.attendance.queries import leave as leave_q
from apps.attendance.serializers.leave import (
    AuditEntrySerializer,
    CreateLeaveSerializer,
    LeaveRequestSerializer,
    ReviewLeaveSerializer,
)


class LeaveListCreateView(APIView):
    permission_classes = [IsAuthenticated]  # students/parents apply; admin/faculty list

    def get(self, request) -> Response:
        # Listing the queue is for faculty/admin.
        if not IsFacultyOrAdmin().has_permission(request, self):
            return Response({"error": "Faculty or admin access required."}, status=http.HTTP_403_FORBIDDEN)
        branch = resolve_branch(request)
        leaves = leave_q.list_leaves(branch.pk, status=request.query_params.get("status"))
        return Response({"leaves": LeaveRequestSerializer(leaves, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        s = CreateLeaveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        leave = leave_i.apply_student_leave(
            branch=branch, student_id=d["studentId"], from_date=d["fromDate"],
            to_date=d["toDate"], reason=d.get("reason", ""), applied_by=request.user,
        )
        return Response({"leave": LeaveRequestSerializer(leave).data}, status=http.HTTP_201_CREATED)


class LeaveReviewView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def patch(self, request, leave_id) -> Response:
        branch = resolve_branch(request)
        leave = leave_q.get_leave(branch.pk, leave_id)
        if not leave:
            return Response({"error": "Not found."}, status=http.HTTP_404_NOT_FOUND)
        s = ReviewLeaveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        leave = leave_i.review_leave(
            leave=leave, action=s.validated_data["action"],
            note=s.validated_data.get("note", ""), reviewer=request.user,
        )
        return Response({"leave": LeaveRequestSerializer(leave).data})


class AuditLogView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        audits = audit_q.list_audits(branch.pk, audit_type=request.query_params.get("type"))
        return Response({"audits": AuditEntrySerializer(audits, many=True).data})
