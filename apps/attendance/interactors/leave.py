"""Interactors — leave application + review workflow (F-106/183/197/213)."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models.user import Role
from apps.attendance.enums import LeaveApplicantRole, LeaveStatus
from apps.attendance.queries import leave as leave_q
from apps.attendance.queries import record as record_q
from apps.attendance.queries import roster as roster_q


@transaction.atomic
def apply_student_leave(*, branch, student_id, from_date, to_date, reason, applied_by):
    """A student (self) or parent applies for leave on a student's behalf."""
    if to_date < from_date:
        raise ValidationError({"toDate": "End date cannot be before start date."})

    student = roster_q.get_student_profile_in_branch(branch.pk, student_id)
    if not student:
        raise ValidationError({"studentId": "Student not found in this branch."})

    if leave_q.overlapping_pending_or_approved(student.pk, from_date, to_date):
        raise ValidationError("An overlapping leave request already exists for this student.")

    return leave_q.create_leave(
        branch_id=branch.pk, applicant_role=LeaveApplicantRole.STUDENT,
        from_date=from_date, to_date=to_date, reason=reason,
        student=student, applied_by=applied_by,
    )


@transaction.atomic
def review_leave(*, leave, action: str, note: str = "", reviewer=None):
    """Faculty/admin approve or reject a leave request (F-106/183)."""
    if reviewer.role not in {Role.ADMIN, Role.SUPER_ADMIN, Role.FACULTY}:
        raise PermissionDenied("Only faculty or admins can review leave.")
    if leave.status != LeaveStatus.PENDING:
        raise ValidationError("Only pending leave requests can be reviewed.")

    if action == "approve":
        leave = leave_q.update_leave(leave, {
            "status": LeaveStatus.APPROVED,
            "approver": reviewer,
            "approved_at": timezone.now(),
            "decision_note": note,
        }, user=reviewer)
        # Retroactively convert any already-marked absences in the range to leave.
        if leave.student_id:
            record_q.set_absent_records_to_leave(
                leave.student_id, leave.from_date, leave.to_date, user=reviewer
            )
    elif action == "reject":
        leave = leave_q.update_leave(leave, {
            "status": LeaveStatus.REJECTED,
            "approver": reviewer,
            "approved_at": timezone.now(),
            "decision_note": note,
        }, user=reviewer)
    else:
        raise ValidationError({"action": "Action must be 'approve' or 'reject'."})

    return leave
