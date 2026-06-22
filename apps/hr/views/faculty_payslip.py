"""Faculty payslip screen — transforms payslips into the FE FacultyPayslipData shape."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fees.helpers.paise import paise_to_rupees_str
from apps.hr.queries import employee as emp_q
from apps.hr.queries import payroll as pay_q

_PROCESSED = {"succeeded", "locked"}


def _month_key(d) -> str:
    return d.strftime("%Y-%m")


def _month_label(d) -> str:
    return d.strftime("%B %Y")


def _status(run) -> str:
    return "processed" if run and run.status in _PROCESSED else "draft"


def _payslip_text(slip) -> str:
    """A plain-text payslip body used as the downloadable content."""
    run = slip.payroll_run
    lines = [
        f"Payslip — {_month_label(run.period_month)}",
        f"Employee: {slip.employee.user.full_name}",
        "",
        "Component                         Amount",
        "----------------------------------------",
    ]
    for c in slip.components or []:
        name = str(c.get("name", c.get("label", "Component")))
        amount = c.get("amountPaise", c.get("amount_paise", 0)) or 0
        lines.append(f"{name[:32]:<32}  {paise_to_rupees_str(int(amount)):>10}")
    lines += [
        "----------------------------------------",
        f"{'Gross':<32}  {paise_to_rupees_str(slip.gross_paise):>10}",
        f"{'Deductions':<32}  {paise_to_rupees_str(slip.deductions_paise):>10}",
        f"{'Net Pay':<32}  {paise_to_rupees_str(slip.net_paise):>10}",
    ]
    return "\n".join(lines)


def _result(slip) -> dict:
    run = slip.payroll_run
    can = run.status in _PROCESSED
    return {
        "canDownload": can,
        "blockedReason": None if can else "Payslip not finalised yet.",
        "fileName": f"payslip-{_month_key(run.period_month)}.txt",
        "content": _payslip_text(slip) if can else "",
        "s3Key": slip.pdf_key or None,
        "downloadUrl": None,
        "downloadUrlExpiresAt": None,
    }


class FacultyPayslipView(APIView):
    """GET → FacultyPayslipData (employee, month options, selected month's result)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        emp = emp_q.get_employee_for_user(request.user.pk)
        if not emp:
            return Response({
                "employeeId": None, "employeeName": None,
                "selectedMonth": "", "months": [], "result": None,
            })

        rows = list(pay_q.list_payslips_for_employee(emp.pk))  # newest first
        by_month = {_month_key(s.payroll_run.period_month): s for s in rows}
        months = [
            {"month": _month_key(s.payroll_run.period_month),
             "label": _month_label(s.payroll_run.period_month),
             "status": _status(s.payroll_run)}
            for s in rows
        ]

        requested = request.query_params.get("month")
        selected = requested if requested in by_month else (months[0]["month"] if months else "")
        slip = by_month.get(selected)

        return Response({
            "employeeId": str(emp.id),
            "employeeName": emp.user.full_name,
            "selectedMonth": selected,
            "months": months,
            "result": _result(slip) if slip else None,
        })
