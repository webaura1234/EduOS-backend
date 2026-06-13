"""Queries — SalaryComponent, PayrollRun, Payslip, PayrollAdjustment (all ORM here).

Immutability (F-164) is enforced HERE: writes to a locked run raise, so no interactor/view
can mutate a locked payroll regardless of call path.
"""

from django.utils import timezone

from apps.hr.enums import PayrollRunStatus
from apps.hr.models import (
    Employee,
    PayrollAdjustment,
    PayrollRun,
    Payslip,
    SalaryComponent,
)


class LockedRunError(Exception):
    """Raised when code attempts to write a payslip into a locked PayrollRun (F-164)."""


# ── Salary components (F-166) ─────────────────────────────────────────────────
def list_components(branch_id, *, active_only=True):
    qs = SalaryComponent.objects.filter(branch_id=branch_id)
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by("kind", "name")


def create_component(*, branch, name, kind, calc, amount_paise=0, percent=0, user=None) -> SalaryComponent:
    return SalaryComponent.objects.create(
        branch=branch, name=name, kind=kind, calc=calc, amount_paise=amount_paise,
        percent=percent, created_by=user, updated_by=user,
    )


# ── Payroll runs ──────────────────────────────────────────────────────────────
def get_run(branch_id, run_id) -> PayrollRun | None:
    try:
        return PayrollRun.objects.select_related("branch").get(
            branch_id=branch_id, pk=run_id, is_active=True
        )
    except (PayrollRun.DoesNotExist, ValueError, TypeError):
        return None


def get_run_for_period(branch_id, period_month) -> PayrollRun | None:
    return PayrollRun.objects.filter(
        branch_id=branch_id, period_month=period_month, is_active=True
    ).first()


def list_runs(branch_id):
    return PayrollRun.objects.filter(branch_id=branch_id, is_active=True).order_by("-period_month")


def create_run(*, branch, period_month, user=None) -> PayrollRun:
    return PayrollRun.objects.create(
        branch=branch, period_month=period_month, status=PayrollRunStatus.RUNNING,
        executed_by=user, created_by=user, updated_by=user,
    )


def update_run(run: PayrollRun, fields: dict, user=None) -> PayrollRun:
    for k, v in fields.items():
        setattr(run, k, v)
    if user:
        run.updated_by = user
    run.save(update_fields=list(fields.keys()) + ["updated_by", "updated_at"])
    return run


def lock_run(run: PayrollRun, user=None) -> PayrollRun:
    run.locked_at = timezone.now()
    run.status = PayrollRunStatus.LOCKED
    if user:
        run.updated_by = user
    run.save(update_fields=["locked_at", "status", "updated_by", "updated_at"])
    return run


# ── Payslips ──────────────────────────────────────────────────────────────────
def create_payslip(*, run: PayrollRun, employee, components, gross_paise, deductions_paise,
                   net_paise, worked_days, payable_days, pro_rated, pdf_key="", user=None) -> Payslip:
    if run.is_locked:
        raise LockedRunError("Cannot add a payslip to a locked payroll run.")
    return Payslip.objects.create(
        payroll_run=run, employee=employee, components=components, gross_paise=gross_paise,
        deductions_paise=deductions_paise, net_paise=net_paise, worked_days=worked_days,
        payable_days=payable_days, pro_rated=pro_rated, pdf_key=pdf_key,
        created_by=user, updated_by=user,
    )


def update_payslip(payslip: Payslip, fields: dict, user=None) -> Payslip:
    if payslip.payroll_run.is_locked:
        raise LockedRunError("Cannot modify a payslip in a locked payroll run.")
    for k, v in fields.items():
        setattr(payslip, k, v)
    payslip.version += 1
    if user:
        payslip.updated_by = user
    payslip.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return payslip


def get_payslip(branch_id, payslip_id) -> Payslip | None:
    try:
        return Payslip.objects.select_related(
            "payroll_run", "employee", "employee__user"
        ).get(payroll_run__branch_id=branch_id, pk=payslip_id, is_active=True)
    except (Payslip.DoesNotExist, ValueError, TypeError):
        return None


def list_payslips_for_run(run_id):
    return Payslip.objects.filter(payroll_run_id=run_id, is_active=True).select_related(
        "employee", "employee__user"
    )


def list_payslips_for_employee(employee_id):
    return Payslip.objects.filter(employee_id=employee_id, is_active=True).select_related(
        "payroll_run"
    ).order_by("-payroll_run__period_month")


# ── Adjustments (F-164) ───────────────────────────────────────────────────────
def create_adjustment(*, branch, employee, original_run, amount_paise, reason, user=None) -> PayrollAdjustment:
    return PayrollAdjustment.objects.create(
        branch=branch, employee=employee, original_run=original_run,
        amount_paise=amount_paise, reason=reason, created_by=user, updated_by=user,
    )


# ── Payable-employee selection (F-169 / EC-DATA-05) ───────────────────────────
def list_payable_employees(branch_id, period_month):
    """Active employees payable at this branch for the month.

    An Employee is 1:1 with a User, so its `branch` is the single salary location
    (EC-DATA-05 / F-161): a multi-branch faculty has additional teaching assignments via
    BranchFaculty, but is paid only at their Employee branch — exactly one payroll. Excludes
    deactivated/exited employees (F-169).
    """
    employees = list(
        Employee.objects.filter(branch_id=branch_id, is_active=True)
        .filter(joined_at__lte=_month_end(period_month))
        .select_related("user")
    )
    return [
        emp for emp in employees
        if not (emp.exited_at and emp.exited_at < period_month)  # exited before month (F-169)
    ]


def _month_end(period_month):
    import calendar
    import datetime
    last = calendar.monthrange(period_month.year, period_month.month)[1]
    return datetime.date(period_month.year, period_month.month, last)
