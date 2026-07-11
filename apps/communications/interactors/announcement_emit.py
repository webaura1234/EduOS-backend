"""Emit in-app notifications when an announcement is published."""

from apps.communications.interactors.create import create_notification
from apps.communications.interactors.recipients import users_for_announcement


def emit_announcement_notifications(announcement, *, created_by) -> int:
    recipients = users_for_announcement(
        branch=announcement.branch,
        target_type=announcement.target_type,
        target_value=announcement.target_value,
    )
    body_preview = (announcement.body or "")[:200]
    if len(announcement.body or "") > 200:
        body_preview += "…"

    count = 0
    for user in recipients:
        child_id = ""
        if user.role == "parent":
            from apps.accounts.models.guardian import StudentGuardianLink
            link = StudentGuardianLink.objects.filter(
                guardian_id=user.pk, is_active=True,
            ).first()
            if link:
                child_id = str(link.student_id)

        variables = {
            "title": announcement.title,
            "announcement_id": str(announcement.pk),
            "body_preview": body_preview,
            "child_id": child_id,
        }
        row = create_notification(
            "announcement.published",
            tenant=announcement.branch.tenant,
            branch=announcement.branch,
            recipient=user,
            variables=variables,
            dedup_key=f"ann:{announcement.pk}:{user.pk}",
            created_by=created_by,
            related_entity_type="announcement",
            related_entity_id=announcement.pk,
        )
        if row:
            count += 1
    return count
