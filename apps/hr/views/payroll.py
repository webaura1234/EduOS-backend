"""Views — salary components, payroll runs, payslips, adjustments (thin)."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.hr.interactors import payroll as pay_i
from apps.hr.queries import employee as emp_q
from apps.hr.queries import payroll as pay_q
from apps.hr.serializers.payroll import (
    CreateAdjustmentSerializer,
    CreateSalaryComponentSerializer,
    PayrollRunSerializer,
    PayslipSerializer,
    RunPayrollSerializer,
    SalaryComponentSerializer,
)


def _step_up_ok(request) -> bool:
    return request.headers.get("X-Step-Up-Verified") == "true"


class SalaryComponentListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        rows = pay_q.list_components(branch.pk)
        return Response({"components": SalaryComponentSerializer(rows, many=True).data})

    def post(self, request):
        branch = resolve_branch(request)
        s = CreateSalaryComponentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        comp = pay_q.create_component(
            branch=branch, name=d["name"], kind=d["kind"], calc=d["calc"],
            amount_paise=d["amountPaise"], percent=d["percent"], user=request.user,
        )
        return Response({"component": SalaryComponentSerializer(comp).data},
                        status=http.HTTP_201_CREATED)


class PayrollRunCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        branch = resolve_branch(request)
        s = RunPayrollSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        run = pay_i.RunPayrollInteractor(
            branch=branch, period_month=s.validated_data["periodMonth"],
            actor=request.user, step_up_verified=_step_up_ok(request),
        ).execute()
        payslips = pay_q.list_payslips_for_run(run.pk)
        return Response({
            "run": PayrollRunSerializer(run).data,
            "payslips": PayslipSerializer(payslips, many=True).data,
        }, status=http.HTTP_201_CREATED)


class PayrollRunDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, run_id):
        branch = resolve_branch(request)
        run = pay_q.get_run(branch.pk, run_id)
        if not run:
            return Response({"error": "Run not found."}, status=http.HTTP_404_NOT_FOUND)
        payslips = pay_q.list_payslips_for_run(run.pk)
        return Response({
            "run": PayrollRunSerializer(run).data,
            "payslips": PayslipSerializer(payslips, many=True).data,
        })


class PayrollRunLockView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, run_id):
        branch = resolve_branch(request)
        run = pay_q.get_run(branch.pk, run_id)
        if not run:
            return Response({"error": "Run not found."}, status=http.HTTP_404_NOT_FOUND)
        run = pay_i.lock_run(run=run, actor=request.user, step_up_verified=_step_up_ok(request))
        return Response({"run": PayrollRunSerializer(run).data})


class PayrollAdjustmentView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        branch = resolve_branch(request)
        s = CreateAdjustmentSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        emp = emp_q.get_employee(branch.pk, d["employeeId"])
        if not emp:
            return Response({"employeeId": "Employee not found."}, status=http.HTTP_404_NOT_FOUND)
        original = pay_q.get_run(branch.pk, d["originalRunId"]) if d.get("originalRunId") else None
        adj = pay_i.create_adjustment(
            branch=branch, employee=emp, original_run=original,
            amount_paise=d["amountPaise"], reason=d["reason"], actor=request.user,
        )
        return Response({"adjustmentId": str(adj.pk)}, status=http.HTTP_201_CREATED)


class PayslipListView(APIView):
    """Admin: all payslips for a run."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, run_id):
        branch = resolve_branch(request)
        run = pay_q.get_run(branch.pk, run_id)
        if not run:
            return Response({"error": "Run not found."}, status=http.HTTP_404_NOT_FOUND)
        rows = pay_q.list_payslips_for_run(run.pk)
        return Response({"payslips": PayslipSerializer(rows, many=True).data})


class MyPayslipsView(APIView):
    """F-165/F-194 — a faculty sees only their own payslips."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        emp = emp_q.get_employee_for_user(request.user.pk)
        if not emp:
            return Response({"payslips": []})
        rows = pay_q.list_payslips_for_employee(emp.pk)
        return Response({"payslips": PayslipSerializer(rows, many=True).data})


class PayslipDetailView(APIView):
    """EC-RBAC-05 — faculty may read only their own payslip; admins read any."""
    permission_classes = [IsAuthenticated]

    def get(self, request, payslip_id):
        branch = resolve_branch(request)
        slip = pay_q.get_payslip(branch.pk, payslip_id)
        if not slip:
            return Response({"error": "Payslip not found."}, status=http.HTTP_404_NOT_FOUND)
        is_admin = request.user.role in {"admin", "super_admin"}
        if not is_admin and slip.employee.user_id != request.user.pk:
            return Response({"error": "You can only view your own payslip."},
                            status=http.HTTP_403_FORBIDDEN)
        return Response({"payslip": PayslipSerializer(slip).data})
