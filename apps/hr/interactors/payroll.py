"""Interactors — payroll run, lock, adjustment (F-158/164/167).

The run is one @transaction.atomic: any failure rolls back ALL payslips (EC-CEL-01).
Immutability (F-164) is enforced in the queries layer (LockedRunError).
"""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.academics.queries import holiday as holiday_q
from apps.accounts.models.user import Role
from apps.hr.enums import PayrollRunStatus
from apps.hr.queries import payroll as pay_q
from apps.hr.services import payroll_calc
from apps.hr.services.pdf import generate_payslip_pdf, store_payslip_pdf


def _holiday_dates(branch_id, period_month):
    start, end = payroll_calc._month_bounds(period_month)
    return [h.date for h in holiday_q.list_holidays(branch_id, from_date=start, to_date=end)]


class RunPayrollInteractor:
    """Compute payslips for all payable employees in a branch for one month (F-158)."""

    def __init__(self, *, branch, period_month, actor=None, step_up_verified=False):
        self.branch = branch
        self.period_month = period_month.replace(day=1)
        self.actor = actor
        self.step_up_verified = step_up_verified

    def execute(self):
        # F-262 seam: payroll.run requires step-up auth.
        if not self.step_up_verified:
            raise PermissionDenied({"code": "step_up_required", "action": "payroll.run"})

        existing = pay_q.get_run_for_period(self.branch.pk, self.period_month)
        if existing:
            raise ValidationError({"periodMonth": "A payroll run already exists for this month."})

        employees = pay_q.list_payable_employees(self.branch.pk, self.period_month)

        # EC-GUARD-15: the executor must not finalize their own payslip line.
        if self.actor and self.actor.role != Role.SUPER_ADMIN:
            actor_group = self.actor.linked_user_group_id
            for emp in employees:
                if emp.user_id == self.actor.pk or (
                    actor_group and emp.user.linked_user_group_id == actor_group
                ):
                    raise PermissionDenied({
                        "code": "self_approve_blocked",
                        "message": "You draw salary in this run; a super-admin must run it.",
                    })

        holidays = _holiday_dates(self.branch.pk, self.period_month)
        institution_name = self.branch.tenant.name
        period_label = self.period_month.strftime("%B %Y")

        try:
            with transaction.atomic():
                run = pay_q.create_run(branch=self.branch, period_month=self.period_month,
                                       user=self.actor)
                gross_total = net_total = 0
                for emp in employees:
                    calc = payroll_calc.compute_for_employee(
                        components=emp.base_components or [],
                        period_month=self.period_month,
                        holiday_dates=holidays,
                        joined_at=emp.joined_at,
                        exited_at=emp.exited_at,
                    )
                    pdf_bytes = generate_payslip_pdf(
                        institution_name=institution_name,
                        employee_name=emp.user.full_name,
                        employee_code=emp.employee_code,
                        period_label=period_label,
                        lines=calc["components"],
                        gross_paise=calc["gross_paise"],
                        deductions_paise=calc["deductions_paise"],
                        net_paise=calc["net_paise"],
                    )
                    pdf_key = store_payslip_pdf(
                        branch_id=self.branch.pk, run_id=run.pk, employee_id=emp.pk,
                        pdf_bytes=pdf_bytes,
                    )
                    pay_q.create_payslip(
                        run=run, employee=emp, components=calc["components"],
                        gross_paise=calc["gross_paise"], deductions_paise=calc["deductions_paise"],
                        net_paise=calc["net_paise"], worked_days=calc["worked_days"],
                        payable_days=calc["payable_days"], pro_rated=calc["pro_rated"],
                        pdf_key=pdf_key, user=self.actor,
                    )
                    gross_total += calc["gross_paise"]
                    net_total += calc["net_paise"]

                pay_q.update_run(run, {
                    "status": PayrollRunStatus.SUCCEEDED,
                    "executed_at": timezone.now(),
                    "totals": {"headcount": len(employees), "grossPaise": gross_total,
                               "netPaise": net_total},
                }, user=self.actor)
        except (PermissionDenied, ValidationError):
            raise
        except Exception as exc:
            # Atomic block already rolled back every payslip (EC-CEL-01); record the failure.
            fail = pay_q.create_run(branch=self.branch, period_month=self.period_month,
                                    user=self.actor)
            pay_q.update_run(fail, {"status": PayrollRunStatus.FAILED,
                                    "error_message": str(exc)}, user=self.actor)
            raise ValidationError({"payroll": f"Payroll run failed and was rolled back: {exc}"})

        return run


@transaction.atomic
def lock_run(*, run, actor=None, step_up_verified=False):
    """F-164 — lock a succeeded run; thereafter no payslip in it can change."""
    if not step_up_verified:
        raise PermissionDenied({"code": "step_up_required", "action": "payroll.lock"})
    if run.is_locked:
        raise ValidationError("Payroll run is already locked.")
    if run.status != PayrollRunStatus.SUCCEEDED:
        raise ValidationError("Only a succeeded run can be locked.")
    return pay_q.lock_run(run, user=actor)


@transaction.atomic
def create_adjustment(*, branch, employee, original_run, amount_paise, reason, actor=None):
    """F-164 — corrections to a locked run go through an adjustment, never an edit."""
    if not reason or not reason.strip():
        raise ValidationError({"reason": "An adjustment reason is required."})
    return pay_q.create_adjustment(
        branch=branch, employee=employee, original_run=original_run,
        amount_paise=amount_paise, reason=reason, user=actor,
    )
