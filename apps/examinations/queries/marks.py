"""Queries — marks entry (all ORM here)."""

from decimal import Decimal

from django.db.models import F
from django.utils import timezone

from apps.examinations.enums import MarksAuditType, MarksStatus
from apps.examinations.models import MarksAudit, MarksEntry


def open_arrear_subjects(enrollment_id) -> list[dict]:
    """Subjects the student has failed in published exams = open arrears (EC-ROL-05 / OD-1).

    Derived from results: a published, submitted/locked mark below the subject's pass mark
    (after grace) is an arrear. Returns [{"subjectId", "subjectName", "examId"}].
    """
    entries = (
        MarksEntry.objects.filter(
            student_id=enrollment_id,
            exam__is_published=True,
            marks_status__in=[MarksStatus.SUBMITTED, MarksStatus.LOCKED],
            is_active=True,
        )
        .select_related("subject", "exam")
    )
    arrears = []
    for e in entries:
        if e.is_absent or e.marks is None:
            continue
        final = e.marks + (e.grace_applied or Decimal("0"))
        if final < e.subject.pass_marks:
            arrears.append({
                "subjectId": str(e.subject_id),
                "subjectName": e.subject.name,
                "examId": str(e.exam_id),
            })
    return arrears


def count_for_subject(subject_id) -> int:
    """Used by academics subject archive guard (EC-DATA-02 / F-096)."""
    return MarksEntry.objects.filter(subject_id=subject_id, is_active=True).count()


def list_marks_for_slot(schedule_slot_id):
    return (
        MarksEntry.objects.filter(
            exam__schedule_slots__id=schedule_slot_id,
            subject_id__in=_slot_subject_ids(schedule_slot_id),
            is_active=True,
        )
        .select_related("student", "student__student_profile__user", "student__batch", "subject", "exam")
        .distinct()
    )


def list_marks_for_slot_by_exam_subject(exam_id, subject_id, batch_id):
    return (
        MarksEntry.objects.filter(
            exam_id=exam_id,
            subject_id=subject_id,
            student__batch_id=batch_id,
            is_active=True,
        )
        .select_related("student", "student__student_profile__user", "student__batch", "subject")
    )


def _slot_subject_ids(schedule_slot_id):
    from apps.examinations.models import ExamScheduleSlot

    try:
        slot = ExamScheduleSlot.objects.get(pk=schedule_slot_id)
        return [slot.subject_id]
    except ExamScheduleSlot.DoesNotExist:
        return []


def get_marks_entry(branch_id, marks_id) -> MarksEntry | None:
    try:
        return MarksEntry.objects.select_related(
            "exam", "subject", "student", "student__student_profile__user", "student__batch"
        ).get(exam__branch_id=branch_id, pk=marks_id, is_active=True)
    except (MarksEntry.DoesNotExist, ValueError, TypeError):
        return None


def get_marks_for_student(exam_id, subject_id, student_id) -> MarksEntry | None:
    try:
        return MarksEntry.objects.get(
            exam_id=exam_id,
            subject_id=subject_id,
            student_id=student_id,
            is_active=True,
        )
    except (MarksEntry.DoesNotExist, ValueError, TypeError):
        return None


def upsert_marks_entry(
    *,
    exam_id,
    subject_id,
    student_id,
    marks,
    is_absent,
    is_internal=False,
    user=None,
) -> MarksEntry:
    entry, created = MarksEntry.objects.get_or_create(
        exam_id=exam_id,
        subject_id=subject_id,
        student_id=student_id,
        defaults={
            "marks": marks,
            "is_absent": is_absent,
            "is_internal": is_internal,
            "marks_status": MarksStatus.DRAFT,
            "created_by": user,
            "updated_by": user,
        },
    )
    if not created:
        if entry.marks_status != MarksStatus.DRAFT:
            return entry
        entry.marks = marks
        entry.is_absent = is_absent
        entry.version += 1
        if user:
            entry.updated_by = user
        entry.save(update_fields=["marks", "is_absent", "version", "updated_by", "updated_at"])
    return entry


def correct_marks_entry(
    entry: MarksEntry,
    *,
    marks,
    is_absent: bool,
    user=None,
) -> MarksEntry:
    """Admin correction of submitted/locked marks (post-publish revision path)."""
    entry.marks = marks
    entry.is_absent = is_absent
    entry.version += 1
    if user:
        entry.updated_by = user
    entry.save(update_fields=["marks", "is_absent", "version", "updated_by", "updated_at"])
    return entry


def update_marks_entry_versioned(
    entry_id,
    *,
    expected_version: int,
    marks,
    is_absent,
    user=None,
) -> MarksEntry | None:
    updated = MarksEntry.objects.filter(
        pk=entry_id,
        version=expected_version,
        marks_status=MarksStatus.DRAFT,
        is_active=True,
    ).update(
        marks=marks,
        is_absent=is_absent,
        version=F("version") + 1,
        updated_by=user,
        updated_at=timezone.now(),
    )
    if updated == 0:
        return None
    return MarksEntry.objects.select_related("student", "student__student_profile__user", "subject", "exam").get(pk=entry_id)


def get_marks_entry_current(entry_id) -> MarksEntry | None:
    try:
        return MarksEntry.objects.get(pk=entry_id, is_active=True)
    except (MarksEntry.DoesNotExist, ValueError, TypeError):
        return None


def submit_marks_for_slot(*, exam_id, subject_id, batch_id, user=None) -> int:
    now = timezone.now()
    return MarksEntry.objects.filter(
        exam_id=exam_id,
        subject_id=subject_id,
        student__batch_id=batch_id,
        marks_status=MarksStatus.DRAFT,
        is_active=True,
    ).update(
        marks_status=MarksStatus.SUBMITTED,
        submitted_at=now,
        version=F("version") + 1,
        updated_by=user,
        updated_at=now,
    )


def list_submitted_marks_for_exam(exam_id):
    """EC-CEL-06 — only submitted/locked marks for GPA recompute."""
    return MarksEntry.objects.filter(
        exam_id=exam_id,
        marks_status__in=[MarksStatus.SUBMITTED, MarksStatus.LOCKED],
        is_active=True,
    )


def create_marks_audit(*, marks_entry_id, audit_type, actor, reason="", metadata=None, user=None):
    return MarksAudit.objects.create(
        marks_entry_id=marks_entry_id,
        audit_type=audit_type,
        actor=actor,
        reason=reason,
        metadata=metadata or {},
        created_by=user,
        updated_by=user,
    )


def marks_value_for_response(entry: MarksEntry):
    if entry.is_absent or entry.marks is None:
        return None
    return float(entry.marks)


def student_linked_to_faculty_group(faculty_user, student_profile) -> bool:
    """EC-GUARD-02 — shared linked_user_group_id or guardian link."""
    from apps.accounts.models.guardian import StudentGuardianLink
    from apps.accounts.models.user import Role

    if not faculty_user or faculty_user.role != Role.FACULTY:
        return False
    group_id = faculty_user.linked_user_group_id
    if not group_id:
        return False
    student_user = student_profile.user
    if student_user.linked_user_group_id == group_id:
        return True
    return StudentGuardianLink.objects.filter(
        student=student_user,
        guardian__linked_user_group_id=group_id,
        is_active=True,
    ).exists()
