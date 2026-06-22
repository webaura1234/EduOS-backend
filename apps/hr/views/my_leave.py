"""Faculty-facing leave — the logged-in employee's own balances + requests + apply."""

import datetime

from rest_framework import status as http
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import holiday as holiday_q
from apps.academics.scoping import resolve_branch
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.hr.interactors import leave as leave_i
from apps.hr.queries import employee as emp_q
from apps.hr.queries import leave as leave_q


def _request(app) -> dict:
    return {
        "id": str(app.id),
        "employeeId": str(app.employee_id),
        "employeeName": app.employee.user.full_name,
        "branchId": str(app.employee.branch_id),
        "branchName": app.employee.branch.name,
        "leaveType": app.leave_type,
        "fromDate": app.from_date.isoformat(),
        "toDate": app.to_date.isoformat(),
        "days": float(app.days),
        "reason": app.reason,
        "status": app.status,
        "requestedAt": app.created_at.isoformat(),
    }


def _balance(b) -> dict:
    return {"leaveType": b.leave_type, "balanceDays": float(b.balance_days)}


class FacultyMyLeaveView(APIView):
    """GET → { balances, requests }; POST { leaveType, fromDate, toDate, reason } → apply."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        emp = emp_q.get_employee_for_user(request.user.pk)
        if not emp:
            return Response({"balances": [], "requests": []})
        requests = leave_q.list_applications(branch.pk, employee_id=emp.pk)
        balances = leave_q.list_balances(emp.pk)
        return Response({
            "balances": [_balance(b) for b in balances],
            "requests": [_request(r) for r in requests],
        })

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        emp = emp_q.get_employee_for_user(request.user.pk)
        if not emp:
            return Response({"error": "No employee record for this user."},
                            status=http.HTTP_400_BAD_REQUEST)
        try:
            from_date = datetime.date.fromisoformat(request.data.get("fromDate"))
            to_date = datetime.date.fromisoformat(request.data.get("toDate"))
        except (TypeError, ValueError):
            raise ValidationError({"fromDate": "Valid fromDate and toDate are required."})

        holidays = [h.date for h in holiday_q.list_holidays(
            branch.pk, from_date=from_date, to_date=to_date)]
        app = leave_i.apply_leave(
            employee=emp, leave_type=request.data.get("leaveType"),
            from_date=from_date, to_date=to_date,
            reason=request.data.get("reason", ""), holiday_dates=holidays,
            actor=request.user,
        )
        return Response({"leave": _request(app)}, status=http.HTTP_201_CREATED)
