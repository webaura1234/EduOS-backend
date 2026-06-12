"""Queries — StudentEnrollment (the enrollment-seam resolver).

All downstream modules (attendance, fees, examinations) resolve a student's
enrollment through these helpers so the seam stays in one place.
"""

from apps.admissions.enums import EnrollmentStatus
from apps.admissions.models import StudentEnrollment


def _branch_of_batch(batch):
    """Derive the owning branch from a batch (Batch → Course → Department → Branch)."""
    if batch is None:
        return None
    return batch.course.department.branch


def list_enrollments(branch_id, *, batch_id=None, academic_year_id=None):
    qs = StudentEnrollment.objects.filter(branch_id=branch_id, is_active=True).select_related(
        "student_profile__user", "batch", "academic_year"
    )
    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    if academic_year_id:
        qs = qs.filter(academic_year_id=academic_year_id)
    return qs.order_by("-created_at")


def get_enrollment_by_id(enrollment_id) -> StudentEnrollment | None:
    try:
        return StudentEnrollment.objects.select_related(
            "student_profile__user", "batch", "academic_year"
        ).get(pk=enrollment_id, is_active=True)
    except (StudentEnrollment.DoesNotExist, ValueError, TypeError):
        return None


def get_active_enrollment_for_profile(profile_id, *, academic_year_id=None) -> StudentEnrollment | None:
    qs = StudentEnrollment.objects.filter(student_profile_id=profile_id, is_active=True)
    if academic_year_id is not None:
        qs = qs.filter(academic_year_id=academic_year_id)
    return qs.select_related("student_profile__user", "batch", "academic_year").order_by(
        "-created_at"
    ).first()


def resolve_enrollment_for_profile(profile, *, batch=None, academic_year=None, user=None,
                                   create=True) -> StudentEnrollment | None:
    """Return the active enrollment for a student profile, creating one if missing.

    The create-if-missing path keeps existing data (seed + downstream tests that only
    build a StudentProfile) valid while the enrollment record becomes the FK anchor.
    Real admission flows create the enrollment explicitly in the provisioning saga.
    """
    batch = batch if batch is not None else profile.current_batch
    if academic_year is None and batch is not None:
        academic_year = batch.academic_year

    existing = StudentEnrollment.objects.filter(
        student_profile_id=profile.pk, is_active=True,
    )
    if academic_year is not None:
        existing = existing.filter(academic_year=academic_year)
    enrollment = existing.select_related(
        "student_profile__user", "batch", "academic_year"
    ).order_by("-created_at").first()
    if enrollment is not None or not create:
        return enrollment

    if academic_year is None:
        return None

    return StudentEnrollment.objects.create(
        branch=_branch_of_batch(batch),
        student_profile=profile,
        batch=batch,
        academic_year=academic_year,
        status=EnrollmentStatus.ACTIVE,
        created_by=user,
        updated_by=user,
    )


def enrollments_in_batch(batch_id):
    """Active enrollments placed in a batch (the class roster, enrollment-keyed)."""
    return (
        StudentEnrollment.objects.filter(
            batch_id=batch_id, status=EnrollmentStatus.ACTIVE, is_active=True
        )
        .select_related("student_profile__user", "batch", "academic_year")
        .order_by("student_profile__user__first_name")
    )


def create_enrollment(*, branch, student_profile, batch, academic_year, application=None,
                      fee_structure_snapshot=None, is_transferred=False,
                      transferred_from_branch=None, backlog_subjects=None,
                      sibling_group_id=None, user=None) -> StudentEnrollment:
    return StudentEnrollment.objects.create(
        branch=branch,
        student_profile=student_profile,
        batch=batch,
        academic_year=academic_year,
        application=application,
        fee_structure_snapshot=fee_structure_snapshot,
        is_transferred=is_transferred,
        transferred_from_branch=transferred_from_branch,
        backlog_subjects=backlog_subjects or [],
        sibling_group_id=sibling_group_id,
        status=EnrollmentStatus.ACTIVE,
        created_by=user,
        updated_by=user,
    )


def soft_delete_enrollment_by_id(enrollment_id, user=None) -> bool:
    """Soft-delete an enrollment created by a rollover run (undo, EC-ROL-02)."""
    enr = StudentEnrollment.objects.filter(pk=enrollment_id, is_active=True).first()
    if not enr:
        return False
    enr.is_active = False
    enr.status = EnrollmentStatus.WITHDRAWN
    if user:
        enr.updated_by = user
    enr.save(update_fields=["is_active", "status", "updated_by", "updated_at"])
    return True


def update_enrollment(enrollment: StudentEnrollment, fields: dict, user=None) -> StudentEnrollment:
    for k, v in fields.items():
        setattr(enrollment, k, v)
    if user:
        enrollment.updated_by = user
    update_fields = list(fields.keys()) + ["updated_at"]
    if user:
        update_fields.append("updated_by")
    enrollment.save(update_fields=update_fields)
    return enrollment
