"""Role-aware deep links for notifications."""

from apps.accounts.models.user import Role


def build_action_url(
    notification_type: str,
    *,
    role: str,
    variables: dict,
) -> str:
    child_id = variables.get("child_id", "")
    child_qs = f"?childId={child_id}" if child_id else ""

    if notification_type.startswith("fee."):
        if role == Role.PARENT:
            return f"/parent/fees{child_qs}"
        if role == Role.STUDENT:
            return "/student/fees"
        if role in (Role.ADMIN, Role.SUPER_ADMIN):
            return "/admin/fees"
        return "/student/fees"

    if notification_type.startswith("attendance."):
        if role == Role.PARENT:
            return f"/parent/attendance{child_qs}"
        if role == Role.STUDENT:
            return "/student/attendance"
        if role in (Role.ADMIN, Role.SUPER_ADMIN):
            return "/admin/attendance"
        return "/student/attendance"

    if notification_type == "examination.results_published":
        exam_id = variables.get("exam_id", "")
        if role == Role.PARENT:
            return f"/parent/exams{child_qs}"
        if role == Role.STUDENT and exam_id:
            return f"/student/exams/results/{exam_id}"
        if role in (Role.ADMIN, Role.SUPER_ADMIN):
            return "/admin/exams"
        return "/student/exams"

    if notification_type == "admissions.status_updated":
        app_id = variables.get("application_id", "")
        if role == Role.PARENT:
            return f"/parent/admissions{child_qs}"
        if role in (Role.ADMIN, Role.SUPER_ADMIN) and app_id:
            return f"/admin/admissions/{app_id}"
        return "/admin/admissions"

    if notification_type.startswith("academics.promotion_"):
        if role == Role.PARENT:
            return f"/parent/account{child_qs}"
        if role == Role.STUDENT:
            return "/student/account"
        if role in (Role.ADMIN, Role.SUPER_ADMIN):
            return "/admin/academic-management"
        return "/student/account"

    if notification_type == "announcement.published":
        ann_id = variables.get("announcement_id", "")
        if role == Role.STUDENT and ann_id:
            return f"/student/notices?id={ann_id}"
        if role == Role.PARENT:
            return "/parent/account?tab=notices"
        if role == Role.FACULTY:
            return "/faculty/account?tab=notices"
        if role in (Role.ADMIN, Role.SUPER_ADMIN):
            return "/admin/engagement?tab=announcements"
        return "/student/notices"

    return "/"
