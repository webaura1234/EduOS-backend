"""Queries — admin academics extras: substitutions, study materials, calendar changes,
working days, and the derived admin review queue."""

from apps.academics.models import (
    AcademicSubstitution,
    CalendarChange,
    StudyMaterial,
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


# ── Study materials ───────────────────────────────────────────────────────────

def list_study_materials(branch_id):
    return (
        StudyMaterial.objects.filter(branch_id=branch_id, is_active=True)
        .select_related("batch__course")
        .order_by("-created_at")
    )


def list_materials_for_batch(branch_id, batch_id):
    """Study materials for a class/batch (student-facing)."""
    return (
        StudyMaterial.objects.filter(branch_id=branch_id, batch_id=batch_id, is_active=True)
        .select_related("batch__course")
        .order_by("-created_at")
    )


def list_materials_for_batches(branch_id, batch_ids):
    """Study materials for a set of classes (faculty-facing — their assigned classes)."""
    return (
        StudyMaterial.objects.filter(
            branch_id=branch_id, batch_id__in=list(batch_ids), is_active=True,
        )
        .select_related("batch__course")
        .order_by("-created_at")
    )


def get_study_material(branch_id, material_id) -> StudyMaterial | None:
    try:
        return StudyMaterial.objects.get(branch_id=branch_id, pk=material_id, is_active=True)
    except (StudyMaterial.DoesNotExist, ValueError, TypeError):
        return None


def create_study_material(*, branch, batch, file_name, s3_key="", url="", user=None) -> StudyMaterial:
    return StudyMaterial.objects.create(
        branch=branch, batch=batch, file_name=file_name, s3_key=s3_key, url=url,
        uploaded_by=user, created_by=user, updated_by=user,
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

def review_entries(branch_id):
    """(tbd_entry_ids, faculty_unassigned_entry_ids) for the admin review queue."""
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
    return [str(i) for i in tbd], [str(i) for i in unassigned]
