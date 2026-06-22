"""Queries — Announcement reads/writes."""

from django.db.models import Q

from apps.communications.models import Announcement


def list_for_branch(branch_id):
    return Announcement.objects.filter(branch_id=branch_id, is_active=True).order_by("-created_at")


def list_for_student(branch_id, batch_id=None):
    """Announcements a student should see: everyone, their batch, or role=student."""
    visible = Q(target_type="all") | Q(target_type="role", target_value="student")
    if batch_id:
        visible |= Q(target_type="batch", target_value=str(batch_id))
    return (
        Announcement.objects.filter(branch_id=branch_id, is_active=True)
        .filter(visible)
        .order_by("-created_at")
    )


def list_for_faculty(branch_id):
    """Announcements a faculty member should see: everyone or role=faculty/staff."""
    return (
        Announcement.objects.filter(branch_id=branch_id, is_active=True)
        .filter(
            Q(target_type="all")
            | Q(target_type="role", target_value__in=["faculty", "staff"])
        )
        .order_by("-created_at")
    )


def create_announcement(*, branch, title, body, target_type, target_value="",
                        target_label="", scope="branch", channels=None,
                        recipient_count=0, user=None) -> Announcement:
    return Announcement.objects.create(
        branch=branch, title=title, body=body, target_type=target_type,
        target_value=target_value, target_label=target_label, scope=scope,
        channels=channels or [], recipient_count=recipient_count,
        created_by=user, updated_by=user,
    )
