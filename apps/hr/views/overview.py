"""Admin HR overview — the tenant-wide HrData aggregate the admin HR screen consumes."""

import datetime

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.accounts.queries.user import list_admins_in_tenant
from apps.hr.queries import employee as emp_q
from apps.hr.queries import leave as leave_q
from apps.hr.queries import payroll as pay_q
from apps.hr.queries import staff_attendance as sa_q


def _rupees(paise: int) -> float:
    return round((paise or 0) / 100, 2)


class AdminHROverviewView(APIView):
    """GET → HrData aggregate scoped to the caller's branch (admin operates on own campus only)."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        tenant_id = request.user.tenant_id
        bid, bname = str(branch.id), branch.name

        employees, leave_requests, payroll_runs, component_templates = [], [], [], []
        today = datetime.date.today()

        for emp in emp_q.list_employees(branch.id, active_only=False):
            summary = sa_q.month_attendance_summary(emp.user_id, branch, today.year, today.month)
            employees.append({
                "id": str(emp.id),
                "name": emp.user.full_name,
                "roleLabel": emp.user.get_role_display(),
                "employmentType": emp.employment_type,
                "primaryBranchId": bid,
                "primaryBranchName": bname,
                "active": emp.is_active,
                "joinedAt": emp.joined_at.isoformat() if emp.joined_at else "",
                "exitedAt": emp.exited_at.isoformat() if emp.exited_at else None,
                "presentDays": summary["presentDays"],
                "absentDays": summary["absentDays"],
                "leaveDays": summary["leaveDays"],
            })

        for app in leave_q.list_applications(branch.id):
            leave_requests.append({
                "id": str(app.id),
                "employeeId": str(app.employee_id),
                "employeeName": app.employee.user.full_name,
                "branchId": bid,
                "branchName": bname,
                "leaveType": app.leave_type,
                "fromDate": app.from_date.isoformat(),
                "toDate": app.to_date.isoformat(),
                "days": float(app.days),
                "reason": app.reason,
                "status": app.status,
                "requestedAt": app.created_at.isoformat(),
            })

        for comp in pay_q.list_components(branch.id):
            component_templates.append({
                "id": str(comp.id),
                "name": comp.name,
                "kind": comp.kind,
                "amount": _rupees(comp.amount_paise),
                "amountPaise": comp.amount_paise,
                "active": comp.is_active,
                "createdAt": comp.created_at.isoformat(),
            })

        for run in pay_q.list_runs(branch.id):
            totals = run.totals or {}
            payroll_runs.append({
                "id": str(run.id),
                "month": run.period_month.strftime("%Y-%m"),
                "branchId": bid,
                "branchName": bname,
                "status": "processed" if run.is_locked else "draft",
                "components": [],
                "employeeCount": totals.get("headcount", 0),
                "totalGross": _rupees(totals.get("grossPaise", 0)),
                "totalNet": _rupees(totals.get("netPaise", 0)),
                "processedAt": run.executed_at.isoformat() if run.executed_at else None,
                "immutable": run.is_locked,
                "adjustments": [],
            })

        branch_admins = [
            {
                "branchId": str(a.branch_id) if a.branch_id else "",
                "branchName": a.branch.name if a.branch_id else "",
                "adminUserId": str(a.id),
                "adminName": a.full_name,
            }
            for a in list_admins_in_tenant(tenant_id)
            if a.branch_id == branch.id
        ]

        available_faculty = [
            {
                "userId": str(u.id),
                "name": u.full_name,
                "employeeCode": u.custom_login_id or f"FAC-{str(u.id)[:8].upper()}",
                "roleLabel": u.get_role_display(),
            }
            for u in emp_q.list_faculty_without_employee(branch.id)
        ]

        return Response({
            "branches": [{"id": bid, "name": bname}],
            "branchAdmins": branch_admins,
            "employees": employees,
            "availableFaculty": available_faculty,
            "assignments": [],
            "leaveBalances": [],
            "leaveRequests": leave_requests,
            "payrollRuns": payroll_runs,
            "componentTemplates": component_templates,
            "documents": [],
        })
