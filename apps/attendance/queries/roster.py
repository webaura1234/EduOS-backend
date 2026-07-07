"""Queries — cross-domain reads attendance needs (students, holidays).

Kept here so all DB access stays in the queries layer.
"""

from django.db.models import Count

from apps.academics.models import Holiday
from apps.accounts.models.profile import StudentProfile
from apps.admissions.enums import EnrollmentStatus
from apps.admissions.models import StudentEnrollment
from apps.admissions.queries import enrollment as enrollment_q
from apps.organizations.models import TenantSettings

# NOTE (enrollment seam, Stage 5 / OD-1 A): the "student" the rest of attendance works
# with is now a StudentEnrollment (it mirrors the StudentProfile API via convenience
# properties `.user`/`.current_batch`/`.academic_status`). The API's `studentId` stays the
# StudentProfile id; these helpers resolve that to the enrollment record.


def all_active_students_in_branch(branch_id):
    """Active enrollments across all batches of a branch."""
    return (
        StudentEnrollment.objects.filter(
            branch_id=branch_id,
            status=EnrollmentStatus.ACTIVE,
            is_active=True,
        )
        .select_related("student_profile__user", "batch")
        .order_by("student_profile__user__first_name")
    )


def active_student_counts_by_branch(branch_ids) -> dict:
    """Active-enrollment counts per branch: ``{branch_id: count}``.

    One grouped query so the super-admin dashboard doesn't run a per-branch
    ``.count()``. Each value equals ``all_active_students_in_branch(bid).count()``.
    """
    rows = (
        StudentEnrollment.objects.filter(
            branch_id__in=branch_ids,
            status=EnrollmentStatus.ACTIVE,
            is_active=True,
        )
        .values("branch_id")
        .annotate(n=Count("id"))
    )
    return {row["branch_id"]: row["n"] for row in rows}


def attendance_config(branch) -> tuple[int, bool]:
    """(threshold_percent, exam_day_counts_toward_attendance) for a branch's tenant."""
    try:
        s = branch.tenant.tenant_settings
        return s.attendance_threshold_percent, s.exam_day_counts_toward_attendance
    except (TenantSettings.DoesNotExist, AttributeError):
        return 75, True


def attendance_mode(branch) -> str:
    """'day' or 'session' for a branch's tenant (default session)."""
    try:
        return branch.tenant.tenant_settings.attendance_mode
    except (TenantSettings.DoesNotExist, AttributeError):
        from apps.organizations.enums import AttendanceMode
        return AttendanceMode.SESSION


def students_in_batch(batch_id):
    """Active enrollments currently placed in a batch (the class roster)."""
    return enrollment_q.enrollments_in_batch(batch_id)


def student_ids_in_batch(batch_id) -> list:
    return list(students_in_batch(batch_id).values_list("id", flat=True))


def roster_counts_for_batches(batch_ids) -> dict[str, int]:
    """Active enrollment count per batch — batch_id (str) → roster size."""
    if not batch_ids:
        return {}
    rows = (
        StudentEnrollment.objects.filter(
            batch_id__in=batch_ids,
            status=EnrollmentStatus.ACTIVE,
            is_active=True,
        )
        .values("batch_id")
        .annotate(n=Count("id"))
    )
    return {str(row["batch_id"]): row["n"] for row in rows}


def get_student_profile_in_branch(branch_id, student_id):
    """Resolve the API's `studentId` (a StudentProfile id) to that student's active
    enrollment within the branch, creating it if missing (enrollment-seam shim)."""
    try:
        profile = StudentProfile.objects.select_related("user", "current_batch").get(
            pk=student_id,
            current_batch__course__department__branch_id=branch_id,
            is_active=True,
        )
    except (StudentProfile.DoesNotExist, ValueError, TypeError):
        return None
    return enrollment_q.resolve_enrollment_for_profile(profile)


def resolve_students_for_marking(branch_id, student_ids: list) -> dict:
    """Bulk equivalent of ``get_student_profile_in_branch`` for a whole mark-session
    payload — ~2 queries total instead of one ``get_student_profile_in_branch`` call
    (itself 2 queries) per student, the dominant cost of marking a large class.

    Returns ``{studentId (str): StudentEnrollment | None}``; ``None`` means no active
    profile was found for that id in this branch. Profiles with no existing
    enrollment fall back to the same auto-create path ``get_student_profile_in_branch``
    uses, one at a time — a rare edge case (a profile with zero enrollments yet), so
    falling back per-id there doesn't reintroduce the N+1 for the common case.
    """
    if not student_ids:
        return {}

    profiles = list(
        StudentProfile.objects.select_related("user", "current_batch").filter(
            pk__in=student_ids,
            current_batch__course__department__branch_id=branch_id,
            is_active=True,
        )
    )
    profile_by_id = {str(p.pk): p for p in profiles}

    enrollments = (
        StudentEnrollment.objects.filter(
            student_profile_id__in=[p.pk for p in profiles], is_active=True,
        )
        .select_related("student_profile__user", "batch", "academic_year")
        .order_by("student_profile_id", "-created_at")
    )
    enrollment_by_profile_id = {}
    for e in enrollments:
        key = str(e.student_profile_id)
        enrollment_by_profile_id.setdefault(key, e)  # first per id = most recent

    result: dict = {}
    for sid in student_ids:
        profile = profile_by_id.get(str(sid))
        if profile is None:
            result[str(sid)] = None
            continue
        enrollment = enrollment_by_profile_id.get(str(profile.pk))
        if enrollment is None:
            enrollment = enrollment_q.resolve_enrollment_for_profile(profile)
        result[str(sid)] = enrollment
    return result


def student_for_guardian(guardian_user_id, student_profile_id):
    """Return the student's active enrollment only if this parent is linked (F-112)."""
    from apps.accounts.models.guardian import StudentGuardianLink

    link = StudentGuardianLink.objects.filter(
        guardian_id=guardian_user_id, student__student_profile__pk=student_profile_id,
        is_active=True,
    ).select_related("student__student_profile", "student__student_profile__current_batch").first()
    if not link:
        return None
    return enrollment_q.resolve_enrollment_for_profile(link.student.student_profile)


def is_student_holiday(branch_id, date) -> bool:
    """True if a holiday on `date` for this branch applies to students (EC-ATT-01)."""
    holidays = Holiday.objects.filter(branch_id=branch_id, date=date, is_active=True)
    for h in holidays:
        applies = h.applies_to or {}
        if applies.get("all"):
            return True
        if "student" in (applies.get("roles") or []):
            return True
        # An empty/unspecified applies_to defaults to everyone.
        if not applies:
            return True
    return False
