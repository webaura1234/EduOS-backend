"""Interactor — retroactive attendance correction (F-107 / EC-ATT-04)."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.attendance.interactors import live_board as live_i
from apps.attendance.enums import AuditType
from apps.attendance.queries import audit as audit_q
from apps.attendance.queries import record as record_q


@transaction.atomic
def correct_record(*, record, new_status, reason="", user=None):
    """
    Admin edits a past record. The original status is preserved in an immutable
    audit diff (EC-ATT-04). Blocked in a frozen academic year.
    """
    if record.session.batch_subject.batch.academic_year.is_frozen:
        raise ValidationError("Cannot correct attendance in a frozen academic year.")

    original = record.status
    if original == new_status:
        raise ValidationError({"newStatus": "New status is the same as the current status."})

    record = record_q.apply_correction(record, new_status, user=user)
    audit_q.create_audit(
        record=record, audit_type=AuditType.RETROACTIVE_EDIT, actor=user,
        original_status=original, new_status=new_status, reason=reason,
    )
    live_i.invalidate_live_cache(record.session.branch_id, record.session.date)
    return record
