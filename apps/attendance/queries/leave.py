"""Queries — LeaveRequest (all ORM for leave)."""

from django.db.models import Q

from apps.attendance.enums import LeaveStatus
from apps.attendance.models import LeaveRequest


def get_leave(branch_id, leave_id) -> LeaveRequest | None:
    try:
        return LeaveRequest.objects.select_related("student", "employee").get(
            branch_id=branch_id, pk=leave_id, is_active=True
        )
    except (LeaveRequest.DoesNotExist, ValueError, TypeError):
        return None


def list_leaves(branch_id, *, status=None, student_id=None):
    qs = LeaveRequest.objects.filter(branch_id=branch_id, is_active=True).select_related(
        "student", "student__student_profile__user", "student__batch",
        "employee", "approver",
    )
    if status:
        qs = qs.filter(status=status)
    if student_id:
        qs = qs.filter(student_id=student_id)
    return qs.order_by("-created_at")


def create_leave(*, branch_id, applicant_role, from_date, to_date, reason,
                 student=None, employee=None, applied_by=None) -> LeaveRequest:
    return LeaveRequest.objects.create(
        branch_id=branch_id, applicant_role=applicant_role, from_date=from_date, to_date=to_date,
        reason=reason, student=student, employee=employee, applied_by=applied_by,
        created_by=applied_by, updated_by=applied_by,
    )


def update_leave(leave: LeaveRequest, fields: dict, user=None) -> LeaveRequest:
    for k, v in fields.items():
        setattr(leave, k, v)
    if fields:
        leave.version += 1
        if user:
            leave.updated_by = user
        leave.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return leave


def has_approved_leave(student_id, date) -> bool:
    """True if the student has an approved leave covering `date` (drives status=leave)."""
    return LeaveRequest.objects.filter(
        student_id=student_id, status=LeaveStatus.APPROVED,
        from_date__lte=date, to_date__gte=date, is_active=True,
    ).exists()


def approved_leave_student_ids_on(date, student_ids):
    """Subset of student_ids that have an approved leave covering `date`."""
    return set(
        LeaveRequest.objects.filter(
            student_id__in=student_ids, status=LeaveStatus.APPROVED,
            from_date__lte=date, to_date__gte=date, is_active=True,
        ).values_list("student_id", flat=True)
    )


def overlapping_pending_or_approved(student_id, from_date, to_date) -> bool:
    """Prevent duplicate overlapping leave applications for the same student."""
    return LeaveRequest.objects.filter(
        student_id=student_id,
        status__in=[LeaveStatus.PENDING, LeaveStatus.APPROVED],
        is_active=True,
    ).filter(Q(from_date__lte=to_date) & Q(to_date__gte=from_date)).exists()
