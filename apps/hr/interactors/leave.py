"""Interactors — staff leave apply + decide, with balances and COI routing (F-157/162/163)."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models.user import Role
from apps.fees.helpers.paise import financial_year_for
from apps.hr.enums import LeaveStatus, LeaveType
from apps.hr.queries import leave as leave_q
from apps.hr.services.payroll_calc import working_days_between


@transaction.atomic
def apply_leave(*, employee, leave_type, from_date, to_date, reason="", holiday_dates=None, actor=None):
    if to_date < from_date:
        raise ValidationError({"toDate": "End date cannot be before start date."})

    days = Decimal(working_days_between(from_date, to_date, holiday_dates))
    if days <= 0:
        raise ValidationError("Leave range contains no working days.")

    if leave_q.overlapping_leave(employee.pk, from_date, to_date):
        raise ValidationError("An overlapping leave request already exists.")

    # Paid leave: soft balance check at apply time (authoritative decrement on approve).
    if leave_type != LeaveType.UNPAID:
        year = financial_year_for(from_date)
        bal = next(
            (b for b in leave_q.list_balances(employee.pk)
             if b.leave_type == leave_type and b.year == year),
            None,
        )
        available = bal.balance_days if bal else Decimal("0")
        if available < days:
            raise ValidationError(
                {"days": f"Insufficient {leave_type} balance ({available} < {days})."}
            )

    return leave_q.create_application(
        employee=employee, leave_type=leave_type, from_date=from_date, to_date=to_date,
        days=days, reason=reason, user=actor,
    )


def decide_leave(*, application, action, reviewer, note=""):
    """Approve/reject a leave; block self-approval (EC-GUARD-03 analog) and move balance."""
    if reviewer.role not in {Role.ADMIN, Role.SUPER_ADMIN, Role.FACULTY}:
        raise PermissionDenied("Only faculty or admins can decide leave.")
    if application.status != LeaveStatus.PENDING:
        raise ValidationError("This leave request has already been decided.")
    if action not in {"approve", "reject"}:
        raise ValidationError({"action": "Action must be 'approve' or 'reject'."})

    # Conflict-of-interest: reviewer is the applicant (same user or linked group) and not a
    # super_admin → hard block, flag for the admin queue (auto-routed).
    applicant_user_id = application.employee.user_id
    applicant_group = application.employee.user.linked_user_group_id
    same_person = reviewer.pk == applicant_user_id
    same_group = bool(applicant_group) and reviewer.linked_user_group_id == applicant_group
    if (same_person or same_group) and reviewer.role != Role.SUPER_ADMIN:
        leave_q.update_application(application, {"auto_routed_coi": True}, user=reviewer)
        raise PermissionDenied("Conflict of interest: routed to the admin/super-admin queue.")

    with transaction.atomic():
        if action == "approve":
            if application.leave_type != LeaveType.UNPAID:
                year = financial_year_for(application.from_date)
                bal = leave_q.get_balance_for_update(application.employee_id,
                                                     application.leave_type, year)
                if bal is None or bal.balance_days < application.days:
                    raise ValidationError("Insufficient leave balance.")
                leave_q.adjust_balance(bal, -application.days, user=reviewer)
            updated, _ = leave_q.update_application(application, {
                "status": LeaveStatus.APPROVED, "approver": reviewer,
                "approved_at": timezone.now(), "decision_note": note,
            }, user=reviewer)
        else:
            updated, _ = leave_q.update_application(application, {
                "status": LeaveStatus.REJECTED, "approver": reviewer,
                "approved_at": timezone.now(), "decision_note": note,
            }, user=reviewer)
    return updated
