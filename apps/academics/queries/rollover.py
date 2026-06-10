"""Queries — Academic year rollover runs."""

from datetime import timedelta

from django.utils import timezone

from apps.academics.models import AcademicRolloverRun, AcademicYear, Batch, RolloverRunStatus
from apps.accounts.models.profile import AcademicStatus, StudentProfile


def get_latest_rollover_run(branch_id) -> AcademicRolloverRun | None:
    return (
        AcademicRolloverRun.objects.filter(branch_id=branch_id, is_active=True)
        .select_related("from_year", "to_year", "executed_by")
        .order_by("-created_at")
        .first()
    )


def get_rollover_run(branch_id, run_id) -> AcademicRolloverRun | None:
    try:
        return AcademicRolloverRun.objects.select_related("from_year", "to_year").get(
            branch_id=branch_id, pk=run_id, is_active=True
        )
    except (AcademicRolloverRun.DoesNotExist, ValueError, TypeError):
        return None


def create_rollover_run(*, branch, from_year, preview_version, user=None) -> AcademicRolloverRun:
    return AcademicRolloverRun.objects.create(
        branch=branch,
        from_year=from_year,
        status=RolloverRunStatus.PENDING,
        preview_version=preview_version,
        created_by=user,
        updated_by=user,
    )


def update_rollover_run(run: AcademicRolloverRun, fields: dict, user=None) -> AcademicRolloverRun:
    for k, v in fields.items():
        setattr(run, k, v)
    if fields:
        run.version += 1
        if user:
            run.updated_by = user
        run.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return run


def list_students_in_year(branch_id, academic_year_id):
    return StudentProfile.objects.filter(
        current_batch__academic_year_id=academic_year_id,
        current_batch__course__department__branch_id=branch_id,
        academic_status=AcademicStatus.ACTIVE,
        is_active=True,
    ).select_related("user", "current_batch", "current_batch__course")


def count_students_in_year(branch_id, academic_year_id) -> int:
    return list_students_in_year(branch_id, academic_year_id).count()


def set_student_batch(profile: StudentProfile, batch_id, user=None):
    profile.current_batch_id = batch_id
    profile.version += 1
    if user:
        profile.updated_by = user
    profile.save(update_fields=["current_batch_id", "version", "updated_by", "updated_at"])


def graduate_student(profile: StudentProfile, user=None):
    profile.academic_status = AcademicStatus.GRADUATED
    profile.current_batch_id = None
    profile.version += 1
    if user:
        profile.updated_by = user
    profile.save(
        update_fields=["academic_status", "current_batch_id", "version", "updated_by", "updated_at"]
    )


def undo_window_active(run: AcademicRolloverRun) -> bool:
    if run.status != RolloverRunStatus.SUCCEEDED:
        return False
    if not run.undo_expires_at:
        return False
    return timezone.now() < run.undo_expires_at


def set_undo_expiry(hours: int = 24):
    return timezone.now() + timedelta(hours=hours)


# ── Lookups/writes used by execute + undo (keep all ORM in queries) ───────────
def get_run_by_id(run_id) -> AcademicRolloverRun | None:
    """Fetch a run by id alone (used by the Celery task), with relations preloaded."""
    try:
        return AcademicRolloverRun.objects.select_related(
            "branch", "branch__tenant", "from_year", "executed_by", "created_by"
        ).get(pk=run_id)
    except (AcademicRolloverRun.DoesNotExist, ValueError, TypeError):
        return None


def get_batches_by_ids(ids) -> list[Batch]:
    return list(Batch.objects.filter(pk__in=ids))


def get_student_profile(user_id) -> StudentProfile | None:
    try:
        return StudentProfile.objects.get(user_id=user_id)
    except (StudentProfile.DoesNotExist, ValueError, TypeError):
        return None


def restore_student(profile: StudentProfile, *, batch_id, academic_status, user=None):
    """Restore a student's batch + status from a rollover snapshot (undo)."""
    profile.current_batch_id = batch_id
    profile.academic_status = academic_status
    profile.version += 1
    if user:
        profile.updated_by = user
    profile.save(
        update_fields=["current_batch_id", "academic_status", "version", "updated_by", "updated_at"]
    )


def get_academic_year(year_id) -> AcademicYear | None:
    try:
        return AcademicYear.objects.get(pk=year_id)
    except (AcademicYear.DoesNotExist, ValueError, TypeError):
        return None


def deactivate_rolled_year(year: AcademicYear, user=None):
    """Soft-delete the newly-created year AND clear is_current in one save.

    Persisting is_current=False here is essential: undo reactivates the old year
    with is_current=True, and two current years would break
    unique_current_academic_year_per_branch.
    """
    year.is_current = False
    year.is_active = False
    if user:
        year.updated_by = user
    year.save(update_fields=["is_current", "is_active", "updated_by", "updated_at"])


def reactivate_year(year: AcademicYear, user=None):
    """Unfreeze the old year and make it current again (undo)."""
    year.is_frozen = False
    year.is_current = True
    if user:
        year.updated_by = user
    year.save(update_fields=["is_frozen", "is_current", "updated_by", "updated_at"])
