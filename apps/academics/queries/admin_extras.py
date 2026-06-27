"""Queries — admin academics extras: substitutions, study materials, calendar changes,
working days, and the derived admin review queue."""

from django.db import models
from django.db.models import Count

from apps.academics.models import (
    AcademicSubstitution,
    BatchFaculty,
    BatchFacultyRole,
    BatchSubject,
    CalendarChange,
    StudyMaterial,
    StudyMaterialFolder,
    Subject,
    TimetableEntry,
    TimetableEntryStatus,
)


# ── Substitutions ─────────────────────────────────────────────────────────────

def list_substitutions(branch_id):
    return (
        AcademicSubstitution.objects.filter(branch_id=branch_id, is_active=True)
        .select_related("original_faculty", "substitute_faculty")
        .order_by("-date")
    )


def get_substitution(branch_id, sub_id) -> AcademicSubstitution | None:
    try:
        return AcademicSubstitution.objects.get(branch_id=branch_id, pk=sub_id, is_active=True)
    except (AcademicSubstitution.DoesNotExist, ValueError, TypeError):
        return None


def create_substitution(*, branch, timetable_entry, original_faculty_id,
                        substitute_faculty_id, date, reason="", user=None) -> AcademicSubstitution:
    return AcademicSubstitution.objects.create(
        branch=branch, timetable_entry=timetable_entry,
        original_faculty_id=original_faculty_id, substitute_faculty_id=substitute_faculty_id,
        date=date, reason=reason, created_by=user, updated_by=user,
    )


def cancel_substitution(sub: AcademicSubstitution, user=None) -> AcademicSubstitution:
    sub.status = "cancelled"
    sub.updated_by = user
    sub.save(update_fields=["status", "updated_by", "updated_at"])
    return sub


def substitutions_for_faculty(branch_id, faculty_id, from_date, to_date):
    """Active substitutions where faculty is original or substitute."""
    return (
        AcademicSubstitution.objects.filter(
            branch_id=branch_id,
            date__gte=from_date,
            date__lte=to_date,
            is_active=True,
        )
        .exclude(status="cancelled")
        .filter(
            models.Q(original_faculty_id=faculty_id) | models.Q(substitute_faculty_id=faculty_id)
        )
        .select_related(
            "timetable_entry",
            "timetable_entry__batch_subject__subject",
            "timetable_entry__period_slot",
            "timetable_entry__timetable__batch",
            "timetable_entry__room",
            "original_faculty",
            "substitute_faculty",
        )
        .order_by("date")
    )


# ── Study material folders ────────────────────────────────────────────────────

def list_folders_for_branch(branch_id):
    return (
        StudyMaterialFolder.objects.filter(branch_id=branch_id, is_active=True)
        .annotate(material_count=Count("materials", filter=models.Q(materials__is_active=True)))
        .select_related("batch__course")
        .order_by("batch_id", "sort_order", "name")
    )


def list_folders_for_batch(branch_id, batch_id):
    return (
        StudyMaterialFolder.objects.filter(
            branch_id=branch_id, batch_id=batch_id, is_active=True,
        )
        .annotate(material_count=Count("materials", filter=models.Q(materials__is_active=True)))
        .order_by("sort_order", "name")
    )


def get_folder(branch_id, folder_id) -> StudyMaterialFolder | None:
    try:
        return StudyMaterialFolder.objects.select_related("batch__course").get(
            branch_id=branch_id, pk=folder_id, is_active=True,
        )
    except (StudyMaterialFolder.DoesNotExist, ValueError, TypeError):
        return None


def _normalize_folder_name(name: str) -> str:
    return (name or "").strip()


def folder_name_taken(batch_id, name: str, *, exclude_id=None) -> bool:
    normalized = _normalize_folder_name(name)
    if not normalized:
        return False
    qs = StudyMaterialFolder.objects.filter(batch_id=batch_id, is_active=True, name__iexact=normalized)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def create_folder(*, branch, batch, name, user=None) -> StudyMaterialFolder:
    clean = _normalize_folder_name(name)
    max_order = (
        StudyMaterialFolder.objects.filter(batch_id=batch.pk, is_active=True)
        .aggregate(m=models.Max("sort_order"))["m"]
    )
    return StudyMaterialFolder.objects.create(
        branch=branch, batch=batch, name=clean,
        sort_order=(max_order or 0) + 1,
        created_by=user, updated_by=user,
    )


def rename_folder(folder: StudyMaterialFolder, name, user=None) -> StudyMaterialFolder:
    folder.name = _normalize_folder_name(name)
    folder.updated_by = user
    folder.save(update_fields=["name", "updated_by", "updated_at"])
    return folder


def delete_folder(folder: StudyMaterialFolder, user=None) -> None:
    folder.is_active = False
    folder.updated_by = user
    folder.save(update_fields=["is_active", "updated_by", "updated_at"])


def folder_material_count(folder_id) -> int:
    return StudyMaterial.objects.filter(folder_id=folder_id, is_active=True).count()


# ── Study materials ───────────────────────────────────────────────────────────

def list_study_materials(branch_id):
    return (
        StudyMaterial.objects.filter(branch_id=branch_id, is_active=True)
        .select_related("batch__course", "folder")
        .order_by("batch_id", "folder__sort_order", "folder__name", "-created_at")
    )


def list_materials_for_batch(branch_id, batch_id):
    """Study materials for a class/batch (student-facing)."""
    return (
        StudyMaterial.objects.filter(branch_id=branch_id, batch_id=batch_id, is_active=True)
        .select_related("batch__course", "folder")
        .order_by("folder__sort_order", "folder__name", "-created_at")
    )


def list_materials_for_batches(branch_id, batch_ids):
    """Study materials for a set of classes (faculty-facing — their assigned classes)."""
    return (
        StudyMaterial.objects.filter(
            branch_id=branch_id, batch_id__in=list(batch_ids), is_active=True,
        )
        .select_related("batch__course", "folder")
        .order_by("batch_id", "folder__sort_order", "folder__name", "-created_at")
    )


def get_study_material(branch_id, material_id) -> StudyMaterial | None:
    try:
        return StudyMaterial.objects.select_related("batch__course", "folder").get(
            branch_id=branch_id, pk=material_id, is_active=True,
        )
    except (StudyMaterial.DoesNotExist, ValueError, TypeError):
        return None


def create_study_material(*, branch, batch, file_name, folder=None, s3_key="", url="", user=None) -> StudyMaterial:
    return StudyMaterial.objects.create(
        branch=branch, batch=batch, folder=folder, file_name=file_name,
        s3_key=s3_key, url=url, uploaded_by=user, created_by=user, updated_by=user,
    )


def delete_study_material(material: StudyMaterial, user=None) -> None:
    material.is_active = False
    material.updated_by = user
    material.save(update_fields=["is_active", "updated_by", "updated_at"])


# ── Calendar changes / freeze ─────────────────────────────────────────────────

def list_calendar_changes(branch_id):
    return CalendarChange.objects.filter(branch_id=branch_id, is_active=True).order_by("-created_at")


def create_calendar_change(*, branch, change_type, description, effective_date,
                           attendance_frozen_through=None, user=None) -> CalendarChange:
    return CalendarChange.objects.create(
        branch=branch, change_type=change_type, description=description,
        effective_date=effective_date, attendance_frozen_through=attendance_frozen_through,
        created_by=user, updated_by=user,
    )


def latest_frozen_through(branch_id):
    row = (
        CalendarChange.objects.filter(
            branch_id=branch_id, is_active=True, attendance_frozen_through__isnull=False,
        )
        .order_by("-attendance_frozen_through")
        .values_list("attendance_frozen_through", flat=True)
        .first()
    )
    return row


# ── Working days (stored on the branch) ───────────────────────────────────────

def set_working_days(branch, day_numbers: list, user=None):
    branch.working_days = sorted({int(d) for d in day_numbers})
    branch.updated_by = user
    branch.save(update_fields=["working_days", "updated_by", "updated_at"])
    return branch


# ── Admin review queue (derived from timetable state) ─────────────────────────

def review_entries(branch_id, *, academic_period_id=None):
    """(tbd_entry_ids, faculty_unassigned_entry_ids, subject_teacher_gaps) for admin review."""
    tbd = list(
        TimetableEntry.objects.filter(
            timetable__batch__course__department__branch_id=branch_id,
            status=TimetableEntryStatus.TBD, is_active=True,
        ).values_list("id", flat=True)
    )
    unassigned = list(
        TimetableEntry.objects.filter(
            timetable__batch__course__department__branch_id=branch_id,
            status=TimetableEntryStatus.ACTIVE, faculty__isnull=True, is_active=True,
        ).values_list("id", flat=True)
    )
    subject_gaps = []
    if academic_period_id:
        subject_gaps = unassigned_subject_teacher_gaps(branch_id, academic_period_id)
    return [str(i) for i in tbd], [str(i) for i in unassigned], subject_gaps


def unassigned_subject_teacher_gaps(branch_id, academic_period_id) -> list[dict]:
    """Course subjects without an active primary teacher for each batch in the period."""
    batch_subjects = {
        (bs.batch_id, bs.subject_id): bs.pk
        for bs in BatchSubject.objects.filter(
            batch__course__department__branch_id=branch_id,
            academic_period_id=academic_period_id,
            is_active=True,
        ).only("id", "batch_id", "subject_id")
    }
    assigned = set(
        BatchFaculty.objects.filter(
            batch_subject__batch__course__department__branch_id=branch_id,
            batch_subject__academic_period_id=academic_period_id,
            role=BatchFacultyRole.PRIMARY,
            is_active=True,
            ended_at__isnull=True,
        ).values_list("batch_subject__batch_id", "batch_subject__subject_id")
    )
    gaps = []
    subjects_by_course = {}
    for subject in Subject.objects.filter(
        course__department__branch_id=branch_id, is_active=True,
    ).select_related("course"):
        subjects_by_course.setdefault(subject.course_id, []).append(subject)

    from apps.academics.models import Batch

    batches = Batch.objects.filter(
        course__department__branch_id=branch_id, is_active=True,
    ).select_related("course")
    for batch in batches:
        for subject in subjects_by_course.get(batch.course_id, []):
            key = (batch.pk, subject.pk)
            if key in assigned:
                continue
            gaps.append({
                "classSectionId": str(batch.pk),
                "subjectId": str(subject.pk),
                "batchSubjectId": str(batch_subjects[key]) if key in batch_subjects else "",
            })
    return gaps
