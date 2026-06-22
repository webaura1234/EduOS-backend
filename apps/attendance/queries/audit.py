"""Queries — AttendanceAudit (append-only)."""

from apps.attendance.models import AttendanceAudit


def create_audit(*, record, audit_type, actor=None, original_status=None,
                 new_status=None, reason="", metadata=None) -> AttendanceAudit:
    return AttendanceAudit.objects.create(
        record=record, audit_type=audit_type, actor=actor,
        original_status=original_status, new_status=new_status,
        reason=reason, metadata=metadata or {},
        created_by=actor, updated_by=actor,
    )


def list_audits(branch_id, *, audit_type=None):
    qs = (
        AttendanceAudit.objects.filter(
            record__session__branch_id=branch_id, is_active=True
        )
        .select_related(
            "record",
            "record__session__batch",
            "record__session__batch_subject__subject",
            "record__student__student_profile__user",
            "actor",
        )
        .order_by("-created_at")
    )
    if audit_type:
        qs = qs.filter(audit_type=audit_type)
    return qs
