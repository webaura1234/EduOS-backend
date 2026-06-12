"""Queries — cross-domain reads attendance needs (students, holidays).

Kept here so all DB access stays in the queries layer.
"""

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
