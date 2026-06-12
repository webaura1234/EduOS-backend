"""Queries — grade scales, exams, and schedule slots (all ORM here)."""

import datetime

from django.db.models import Q

from apps.academics.models import AcademicPeriod
from apps.examinations.dtos import ExamClashDTO
from apps.examinations.models import Exam, ExamScheduleSlot, GradeScale


def get_period_in_branch(branch_id, period_id) -> AcademicPeriod | None:
    try:
        return AcademicPeriod.objects.select_related("academic_year").get(
            pk=period_id,
            academic_year__branch_id=branch_id,
            is_active=True,
        )
    except (AcademicPeriod.DoesNotExist, ValueError, TypeError):
        return None


# ── GradeScale ────────────────────────────────────────────────────────────────
def list_grade_scales(branch_id, *, course_id=None):
    qs = GradeScale.objects.filter(branch_id=branch_id, is_active=True).select_related("course")
    if course_id:
        qs = qs.filter(course_id=course_id)
    return qs.order_by("name")


def get_grade_scale(branch_id, scale_id) -> GradeScale | None:
    try:
        return GradeScale.objects.select_related("course").get(
            branch_id=branch_id, pk=scale_id, is_active=True
        )
    except (GradeScale.DoesNotExist, ValueError, TypeError):
        return None


def grade_scale_name_exists(branch_id, course_id, name, exclude_id=None) -> bool:
    qs = GradeScale.objects.filter(
        branch_id=branch_id, course_id=course_id, name__iexact=name, is_active=True
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def create_grade_scale(branch_id, *, course_id, name, bands, grace_marks_max=0, is_default=False, user=None):
    return GradeScale.objects.create(
        branch_id=branch_id,
        course_id=course_id,
        name=name,
        bands=bands,
        grace_marks_max=grace_marks_max,
        is_default=is_default,
        created_by=user,
        updated_by=user,
    )


def update_grade_scale(scale: GradeScale, fields: dict, user=None) -> GradeScale:
    for k, v in fields.items():
        setattr(scale, k, v)
    if fields:
        scale.version += 1
        if user:
            scale.updated_by = user
        scale.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return scale


def soft_delete_grade_scale(scale: GradeScale, user=None) -> GradeScale:
    scale.soft_delete(user)
    scale.version += 1
    scale.save(update_fields=["version", "updated_at"])
    return scale


# ── Exam ──────────────────────────────────────────────────────────────────────
def list_exams(branch_id, *, academic_period_id=None):
    qs = Exam.objects.filter(branch_id=branch_id, is_active=True).select_related("academic_period")
    if academic_period_id:
        qs = qs.filter(academic_period_id=academic_period_id)
    return qs.order_by("-created_at")


def get_exam(branch_id, exam_id) -> Exam | None:
    try:
        return Exam.objects.select_related("academic_period", "academic_period__academic_year").get(
            branch_id=branch_id, pk=exam_id, is_active=True
        )
    except (Exam.DoesNotExist, ValueError, TypeError):
        return None


def create_exam(branch_id, *, academic_period_id, name, exam_type, exam_fee_paise=0, marks_deadline=None, user=None):
    return Exam.objects.create(
        branch_id=branch_id,
        academic_period_id=academic_period_id,
        name=name,
        exam_type=exam_type,
        exam_fee_paise=exam_fee_paise,
        marks_deadline=marks_deadline,
        created_by=user,
        updated_by=user,
    )


def update_exam(exam: Exam, fields: dict, user=None) -> Exam:
    for k, v in fields.items():
        setattr(exam, k, v)
    if fields:
        exam.version += 1
        if user:
            exam.updated_by = user
        exam.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return exam


def soft_delete_exam(exam: Exam, user=None) -> Exam:
    exam.soft_delete(user)
    exam.version += 1
    exam.save(update_fields=["version", "updated_at"])
    return exam


# ── ExamScheduleSlot ──────────────────────────────────────────────────────────
def list_schedule_slots(exam_id):
    return (
        ExamScheduleSlot.objects.filter(exam_id=exam_id, is_active=True)
        .select_related("subject", "batch", "room", "exam")
        .order_by("start_at")
    )


def get_schedule_slot(exam_id, slot_id) -> ExamScheduleSlot | None:
    try:
        return ExamScheduleSlot.objects.select_related("subject", "batch", "room", "exam").get(
            exam_id=exam_id, pk=slot_id, is_active=True
        )
    except (ExamScheduleSlot.DoesNotExist, ValueError, TypeError):
        return None


def _overlap_filter(start_at: datetime.datetime, end_at: datetime.datetime) -> Q:
    return Q(start_at__lt=end_at, end_at__gt=start_at)


def find_slot_clashes(
    *,
    branch_id,
    room_id,
    batch_id,
    start_at: datetime.datetime,
    end_at: datetime.datetime,
    exclude_id=None,
) -> list[ExamClashDTO]:
    """Return room and batch overlaps for EC-EXAM-06."""
    overlap = _overlap_filter(start_at, end_at)
    base = ExamScheduleSlot.objects.filter(
        exam__branch_id=branch_id,
        is_active=True,
    ).filter(overlap)
    if exclude_id:
        base = base.exclude(pk=exclude_id)

    clashes: list[ExamClashDTO] = []
    for other in base.select_related("subject", "room", "batch"):
        if str(other.room_id) == str(room_id):
            clashes.append(
                ExamClashDTO(
                    type="room_overlap",
                    slot_id=str(exclude_id or ""),
                    other_slot_id=str(other.pk),
                    message=f"Room {other.room.name} is already booked for {other.subject.name}.",
                )
            )
        if str(other.batch_id) == str(batch_id):
            clashes.append(
                ExamClashDTO(
                    type="class_overlap",
                    slot_id=str(exclude_id or ""),
                    other_slot_id=str(other.pk),
                    message=f"Class {other.batch.name} already has {other.subject.name} scheduled at this time.",
                )
            )
    return clashes


def create_schedule_slot(
    exam_id,
    *,
    subject_id,
    batch_id,
    room_id,
    start_at,
    end_at,
    max_marks,
    max_capacity=None,
    user=None,
) -> ExamScheduleSlot:
    return ExamScheduleSlot.objects.create(
        exam_id=exam_id,
        subject_id=subject_id,
        batch_id=batch_id,
        room_id=room_id,
        start_at=start_at,
        end_at=end_at,
        max_marks=max_marks,
        max_capacity=max_capacity,
        created_by=user,
        updated_by=user,
    )


def update_schedule_slot(slot: ExamScheduleSlot, fields: dict, user=None) -> ExamScheduleSlot:
    for k, v in fields.items():
        setattr(slot, k, v)
    if fields:
        slot.version += 1
        if user:
            slot.updated_by = user
        slot.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return slot


def soft_delete_schedule_slot(slot: ExamScheduleSlot, user=None) -> ExamScheduleSlot:
    slot.soft_delete(user)
    slot.version += 1
    slot.save(update_fields=["version", "updated_at"])
    return slot


def get_schedule_slot_in_branch(branch_id, slot_id) -> ExamScheduleSlot | None:
    try:
        return ExamScheduleSlot.objects.select_related(
            "exam", "subject", "batch", "room", "exam__branch"
        ).get(exam__branch_id=branch_id, pk=slot_id, is_active=True)
    except (ExamScheduleSlot.DoesNotExist, ValueError, TypeError):
        return None


def get_schedule_slot_for_marks_entry(entry) -> ExamScheduleSlot | None:
    if not entry.student.current_batch_id:
        return None
    return (
        ExamScheduleSlot.objects.filter(
            exam_id=entry.exam_id,
            subject_id=entry.subject_id,
            batch_id=entry.student.current_batch_id,
            is_active=True,
        )
        .select_related("exam", "subject", "batch", "room")
        .order_by("start_at")
        .first()
    )
