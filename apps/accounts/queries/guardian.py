"""Queries — student-guardian links for the admin Guardian-links screen."""

from apps.accounts.models.guardian import StudentGuardianLink
from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import User


def list_guardian_links(branch_id):
    # student and guardian are both User FKs (student/parent roles).
    return (
        StudentGuardianLink.objects.filter(
            student__branch_id=branch_id, is_active=True,
        )
        .select_related("student", "student__student_profile", "guardian")
        .order_by("student__first_name", "student__last_name")
    )


def get_link(branch_id, link_id) -> StudentGuardianLink | None:
    try:
        return StudentGuardianLink.objects.select_related("student", "guardian").get(
            pk=link_id, student__branch_id=branch_id, is_active=True,
        )
    except (StudentGuardianLink.DoesNotExist, ValueError, TypeError):
        return None


def student_user_from_profile(branch_id, profile_id) -> User | None:
    """Resolve the FE's studentId (a StudentProfile id) to the student User."""
    try:
        profile = StudentProfile.objects.select_related("user").get(
            pk=profile_id, user__branch_id=branch_id,
        )
        return profile.user
    except (StudentProfile.DoesNotExist, ValueError, TypeError):
        # Fall back: the id may already be a student User id.
        return User.objects.filter(pk=profile_id, branch_id=branch_id, role="student").first()


def guardian_user(branch_id, user_id) -> User | None:
    return User.objects.filter(pk=user_id, branch_id=branch_id, role="parent").first()


def create_link(*, student_user, guardian_user, relationship, custody,
                is_primary, has_portal, user=None) -> StudentGuardianLink:
    return StudentGuardianLink.objects.create(
        student=student_user, guardian=guardian_user, relationship=relationship,
        custody=custody, is_primary_contact=is_primary, has_portal_access=has_portal,
        created_by=user, updated_by=user,
    )


def update_link(link: StudentGuardianLink, fields: dict, user=None) -> StudentGuardianLink:
    for key, value in fields.items():
        setattr(link, key, value)
    link.updated_by = user
    link.save(update_fields=list(fields.keys()) + ["updated_by", "updated_at"])
    return link


def remove_link(link: StudentGuardianLink, user=None) -> None:
    link.is_active = False
    link.updated_by = user
    link.save(update_fields=["is_active", "updated_by", "updated_at"])


def set_primary_link(link: StudentGuardianLink, user=None) -> StudentGuardianLink:
    StudentGuardianLink.objects.filter(
        student_id=link.student_id, is_active=True,
    ).exclude(pk=link.pk).update(is_primary_contact=False)
    link.is_primary_contact = True
    link.updated_by = user
    link.save(update_fields=["is_primary_contact", "updated_by", "updated_at"])
    return link
