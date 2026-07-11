"""Attendance notification triggers."""

from django.utils import timezone

from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.attendance.enums import AttendanceStatus
from apps.attendance.interactors.report import student_summary
from apps.communications.interactors.create import create_notification
from apps.communications.interactors.recipients import student_and_guardian_users


def notify_absent(*, branch, session, enrollment, user=None) -> None:
    profile = enrollment.student_profile
    if not profile or not profile.user_id:
        return
    student_user = profile.user
    batch = session.batch
    class_label = batch.name if batch else "—"
    if batch and batch.course_id:
        class_label = f"{batch.course.name} - {batch.name}"
    name = student_user.full_name
    date_str = session.date.isoformat()

    for recipient, extras in student_and_guardian_users(student_user):
        create_notification(
            "attendance.absent",
            tenant=branch.tenant,
            branch=branch,
            recipient=recipient,
            variables={
                "student_name": name,
                "date": date_str,
                "class_label": class_label,
                **extras,
            },
            dedup_key=f"att:absent:{session.pk}:{enrollment.pk}:{recipient.pk}",
            created_by=user,
            related_entity_type="attendance_session",
            related_entity_id=session.pk,
        )


def run_attendance_shortage_scan() -> int:
    """Daily job — warn students below attendance threshold."""
    from apps.accounts.models.profile import StudentProfile

    count = 0
    profiles = StudentProfile.objects.filter(
        is_active=True,
        user__is_active=True,
    ).select_related("user", "user__branch", "user__tenant")

    for profile in profiles:
        user = profile.user
        if not user.branch_id:
            continue
        branch = user.branch
        enrollment = get_active_enrollment_for_profile(profile.pk)
        if not enrollment:
            continue
        try:
            summary = student_summary(branch, enrollment)
        except Exception:
            continue
        pct = summary.get("overallPercent", 100)
        threshold = summary.get("threshold", 75)
        if pct >= threshold:
            continue
        name = user.full_name
        month_key = timezone.localdate().strftime("%Y-%m")
        for recipient, extras in student_and_guardian_users(user):
            if create_notification(
                "attendance.shortage",
                tenant=branch.tenant,
                branch=branch,
                recipient=recipient,
                variables={
                    "student_name": name,
                    "attendance_percent": str(pct),
                    "threshold_percent": str(threshold),
                    **extras,
                },
                dedup_key=f"att:shortage:{user.pk}:{month_key}:{recipient.pk}",
                related_entity_type="student",
                related_entity_id=user.pk,
            ):
                count += 1
    return count


def notify_absent_records(*, branch, session, records, user=None) -> None:
    for record in records:
        if record.status == AttendanceStatus.ABSENT:
            notify_absent(branch=branch, session=session, enrollment=record.student, user=user)
