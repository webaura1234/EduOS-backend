"""Resolve notification recipients for students (student + linked guardians)."""

from apps.accounts.models.guardian import StudentGuardianLink
from apps.accounts.models.user import Role, User


def guardians_for_student(student_user_id) -> list:
    return list(
        StudentGuardianLink.objects.filter(
            student_id=student_user_id, is_active=True, has_portal_access=True,
        ).select_related("guardian")
    )


def student_and_guardian_users(student_user) -> list[tuple[User, dict]]:
    """Return [(user, extra_variables)] for student and each guardian."""
    results = [(student_user, {"child_id": ""})]
    for link in guardians_for_student(student_user.pk):
        g = link.guardian
        if g.is_active:
            results.append((g, {"child_id": str(student_user.pk)}))
    return results


def users_for_announcement(*, branch, target_type, target_value) -> list[User]:
    """Resolve announcement audience to User rows."""
    from apps.academics.models import Batch
    from apps.admissions.models.enrollment import StudentEnrollment
    from apps.admissions.enums import EnrollmentStatus

    qs = User.objects.filter(branch_id=branch.pk, is_active=True)

    if target_type == "all":
        return list(qs)

    if target_type == "role":
        if target_value == "parent":
            return list(qs.filter(role=Role.PARENT))
        if target_value == "student":
            return list(qs.filter(role=Role.STUDENT))
        if target_value in ("faculty", "staff"):
            return list(qs.filter(role=Role.FACULTY))
        return list(qs.filter(role=target_value))

    if target_type == "batch" and target_value:
        student_ids = StudentEnrollment.objects.filter(
            branch_id=branch.pk,
            batch_id=target_value,
            status=EnrollmentStatus.ACTIVE,
            is_active=True,
        ).values_list("student_profile__user_id", flat=True)
        users = list(User.objects.filter(pk__in=student_ids, is_active=True))
        # Also notify guardians of those students
        extra = []
        for u in users:
            for link in guardians_for_student(u.pk):
                if link.guardian.is_active:
                    extra.append(link.guardian)
        return list({u.pk: u for u in users + extra}.values())

    if target_type == "department" and target_value:
        batch_ids = Batch.objects.filter(
            course__department_id=target_value,
            course__department__branch_id=branch.pk,
            is_active=True,
        ).values_list("id", flat=True)
        student_ids = StudentEnrollment.objects.filter(
            branch_id=branch.pk,
            batch_id__in=batch_ids,
            status=EnrollmentStatus.ACTIVE,
            is_active=True,
        ).values_list("student_profile__user_id", flat=True)
        users = list(User.objects.filter(pk__in=student_ids, is_active=True))
        extra = []
        for u in users:
            for link in guardians_for_student(u.pk):
                if link.guardian.is_active:
                    extra.append(link.guardian)
        return list({u.pk: u for u in users + extra}.values())

    return []
