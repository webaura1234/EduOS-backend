"""Parent portal queries — linked children and portal access."""

from apps.accounts.models.guardian import StudentGuardianLink
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile


def _class_label(enrollment) -> str:
    batch = enrollment.batch if enrollment else None
    if not batch:
        return "—"
    course = batch.course.name if batch.course_id else ""
    return f"{course} - {batch.name}" if course else batch.name


def parent_portal_access(tenant) -> dict:
    """Whether the parent portal is enabled for the institution."""
    if tenant is None:
        return {"allowed": True}
    allowed = bool(getattr(tenant, "parent_access_enabled", True))
    if not allowed:
        return {
            "allowed": False,
            "reason": "The parent portal is not available for this institution.",
            "institutionType": tenant.institution_type,
        }
    return {"allowed": True, "institutionType": tenant.institution_type}


def list_portal_children(guardian_user) -> list[dict]:
    """Active linked students visible in the parent portal child switcher."""
    links = (
        StudentGuardianLink.objects.filter(
            guardian=guardian_user,
            is_active=True,
            has_portal_access=True,
            student__is_active=True,
        )
        .select_related("student", "student__student_profile")
        .order_by("student__first_name", "student__last_name")
    )
    children: list[dict] = []
    for link in links:
        student = link.student
        profile = getattr(student, "student_profile", None)
        enrollment = get_active_enrollment_for_profile(profile.pk) if profile else None
        children.append({
            "id": str(student.pk),
            "name": student.full_name,
            "classLabel": _class_label(enrollment),
            "rollNumber": student.custom_login_id or "",
        })
    return children
