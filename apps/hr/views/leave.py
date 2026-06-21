"""Views — staff leave apply / list / decide / balances (thin)."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import holiday as holiday_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.hr.interactors import leave as leave_i
from apps.hr.queries import employee as emp_q
from apps.hr.queries import leave as leave_q
from apps.hr.serializers.leave import (
    ApplyLeaveSerializer,
    DecideLeaveSerializer,
    LeaveApplicationSerializer,
    LeaveBalanceSerializer,
)


class LeaveApplyView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def post(self, request):
        branch = resolve_branch(request)
        s = ApplyLeaveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        employee = emp_q.get_employee(branch.pk, data["employeeId"])
        if not employee:
            return Response({"employeeId": "Employee not found."}, status=http.HTTP_404_NOT_FOUND)
        holidays = [h.date for h in holiday_q.list_holidays(
            branch.pk, from_date=data["fromDate"], to_date=data["toDate"])]
        app = leave_i.apply_leave(
            employee=employee, leave_type=data["leaveType"], from_date=data["fromDate"],
            to_date=data["toDate"], reason=data["reason"], holiday_dates=holidays,
            actor=request.user,
        )
        return Response({"leave": LeaveApplicationSerializer(app).data},
                        status=http.HTTP_201_CREATED)


class LeaveListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        rows = leave_q.list_applications(branch.pk, status=request.query_params.get("status"))
        return Response({"leaves": LeaveApplicationSerializer(rows, many=True).data})


class LeaveDecideView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def patch(self, request, application_id):
        branch = resolve_branch(request)
        app = leave_q.get_application(branch.pk, application_id)
        if not app:
            return Response({"error": "Leave not found."}, status=http.HTTP_404_NOT_FOUND)
        s = DecideLeaveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        from rest_framework.exceptions import PermissionDenied
        try:
            updated = leave_i.decide_leave(
                application=app, action=s.validated_data["action"],
                reviewer=request.user, note=s.validated_data["note"],
            )
            return Response({"leave": LeaveApplicationSerializer(updated).data})
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=http.HTTP_403_FORBIDDEN)


class LeaveBalancesView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request, employee_id):
        branch = resolve_branch(request)
        emp = emp_q.get_employee(branch.pk, employee_id)
        if not emp:
            return Response({"error": "Employee not found."}, status=http.HTTP_404_NOT_FOUND)
        rows = leave_q.list_balances(emp.pk)
        return Response({"balances": LeaveBalanceSerializer(rows, many=True).data})
