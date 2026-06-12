"""
Queries — Subject, BatchSubject, BatchFaculty. Branch-scoped via course hierarchy.
"""

from apps.academics.models import BatchFaculty, BatchSubject, Subject, TimetableEntry, TimetableEntryStatus  # noqa: F401


def list_subjects(branch_id, course_id=None, *, archived_only=False):
    qs = Subject.objects.filter(course__department__branch_id=branch_id).select_related("course")
    if archived_only:
        qs = qs.filter(is_active=False)
    else:
        qs = qs.filter(is_active=True)
    if course_id:
        qs = qs.filter(course_id=course_id)
    return qs.order_by("name")


def get_subject(branch_id, subject_id) -> Subject | None:
    try:
        return Subject.objects.select_related("course").get(
            course__department__branch_id=branch_id, pk=subject_id, is_active=True
        )
    except (Subject.DoesNotExist, ValueError, TypeError):
        return None


def subject_code_exists(course_id, code, exclude_id=None) -> bool:
    if not code:
        return False
    qs = Subject.objects.filter(course_id=course_id, code__iexact=code, is_active=True)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def subject_has_marks(subject_id) -> bool:
    from apps.examinations.queries.marks import count_for_subject

    return count_for_subject(subject_id) > 0


def subject_has_active_timetable_entries(subject_id) -> bool:
    return TimetableEntry.objects.filter(
        batch_subject__subject_id=subject_id,
        status=TimetableEntryStatus.ACTIVE,
        is_active=True,
    ).exists()


def mark_subject_timetable_entries_tbd(subject_id, user=None) -> list:
    entries = TimetableEntry.objects.filter(
        batch_subject__subject_id=subject_id,
        status=TimetableEntryStatus.ACTIVE,
        is_active=True,
    )
    ids = list(entries.values_list("id", flat=True))
    entries.update(status=TimetableEntryStatus.TBD)
    return [str(i) for i in ids]


def create_subject(
    *, course, name, code="", subject_type, max_marks=100, pass_marks=35, credits=None, is_elective=False, user=None
) -> Subject:
    return Subject.objects.create(
        course=course,
        name=name,
        code=code,
        subject_type=subject_type,
        max_marks=max_marks,
        pass_marks=pass_marks,
        credits=credits,
        is_elective=is_elective,
        created_by=user,
        updated_by=user,
    )


def update_subject(subject: Subject, fields: dict, user=None) -> Subject:
    for k, v in fields.items():
        setattr(subject, k, v)
    if fields:
        subject.version += 1
        if user:
            subject.updated_by = user
        subject.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return subject


def soft_delete_subject(subject: Subject, user=None) -> Subject:
    subject.soft_delete(user)
    subject.version += 1
    subject.save(update_fields=["version", "updated_at"])
    return subject


# ── BatchSubject ──────────────────────────────────────────────────────────────
def list_batch_subjects(branch_id, *, batch_id=None, academic_period_id=None):
    qs = BatchSubject.objects.filter(
        batch__course__department__branch_id=branch_id, is_active=True
    ).select_related("batch", "subject", "academic_period")
    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    if academic_period_id:
        qs = qs.filter(academic_period_id=academic_period_id)
    return qs


def get_batch_subject(branch_id, batch_subject_id) -> BatchSubject | None:
    try:
        return BatchSubject.objects.select_related("batch", "subject", "academic_period").get(
            batch__course__department__branch_id=branch_id, pk=batch_subject_id, is_active=True
        )
    except (BatchSubject.DoesNotExist, ValueError, TypeError):
        return None


def batch_subject_exists(batch_id, subject_id, academic_period_id, exclude_id=None) -> bool:
    qs = BatchSubject.objects.filter(
        batch_id=batch_id, subject_id=subject_id, academic_period_id=academic_period_id, is_active=True
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def create_batch_subject(*, batch, subject, academic_period, is_required=True, user=None) -> BatchSubject:
    return BatchSubject.objects.create(
        batch=batch,
        subject=subject,
        academic_period=academic_period,
        is_required=is_required,
        created_by=user,
        updated_by=user,
    )


def update_batch_subject(bs: BatchSubject, fields: dict, user=None) -> BatchSubject:
    for k, v in fields.items():
        setattr(bs, k, v)
    if fields:
        bs.version += 1
        if user:
            bs.updated_by = user
        bs.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return bs


def soft_delete_batch_subject(bs: BatchSubject, user=None) -> BatchSubject:
    bs.soft_delete(user)
    bs.version += 1
    bs.save(update_fields=["version", "updated_at"])
    return bs


# ── BatchFaculty ──────────────────────────────────────────────────────────────
def list_batch_faculty(branch_id, *, batch_subject_id=None):
    qs = BatchFaculty.objects.filter(
        batch_subject__batch__course__department__branch_id=branch_id, is_active=True
    ).select_related("batch_subject", "faculty")
    if batch_subject_id:
        qs = qs.filter(batch_subject_id=batch_subject_id)
    return qs


def get_batch_faculty(branch_id, assignment_id) -> BatchFaculty | None:
    try:
        return BatchFaculty.objects.select_related("batch_subject", "faculty").get(
            batch_subject__batch__course__department__branch_id=branch_id,
            pk=assignment_id,
            is_active=True,
        )
    except (BatchFaculty.DoesNotExist, ValueError, TypeError):
        return None


def create_batch_faculty(*, batch_subject, faculty, role, assigned_at, ended_at=None, user=None) -> BatchFaculty:
    return BatchFaculty.objects.create(
        batch_subject=batch_subject,
        faculty=faculty,
        role=role,
        assigned_at=assigned_at,
        ended_at=ended_at,
        created_by=user,
        updated_by=user,
    )


def update_batch_faculty(assignment: BatchFaculty, fields: dict, user=None) -> BatchFaculty:
    for k, v in fields.items():
        setattr(assignment, k, v)
    if fields:
        assignment.version += 1
        if user:
            assignment.updated_by = user
        assignment.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return assignment


def soft_delete_batch_faculty(assignment: BatchFaculty, user=None) -> BatchFaculty:
    assignment.soft_delete(user)
    assignment.version += 1
    assignment.save(update_fields=["version", "updated_at"])
    return assignment
