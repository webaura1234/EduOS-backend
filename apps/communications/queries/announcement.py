"""Queries — Announcement reads/writes."""

from django.db.models import Q

from apps.communications.models import Announcement, AnnouncementRead


def read_ids_for_user(user_id, announcement_ids) -> set:
    """Subset of the given announcement ids that the user has already read."""
    if not announcement_ids:
        return set()
    return set(
        AnnouncementRead.objects.filter(
            user_id=user_id, announcement_id__in=announcement_ids, is_active=True,
        ).values_list("announcement_id", flat=True)
    )


def mark_read(user, announcements) -> int:
    """Mark the given announcements read for the user. Idempotent. Returns count created."""
    existing = read_ids_for_user(user.pk, [a.pk for a in announcements])
    to_create = [
        AnnouncementRead(announcement=a, user=user, created_by=user, updated_by=user)
        for a in announcements if a.pk not in existing
    ]
    if to_create:
        AnnouncementRead.objects.bulk_create(to_create, ignore_conflicts=True)
    return len(to_create)


def list_for_branch(branch_id):
    return (
        Announcement.objects.filter(branch_id=branch_id, is_active=True)
        .select_related("branch")
        .order_by("-created_at")
    )


def list_for_student(branch_id, batch_id=None):
    """Announcements a student should see: everyone, their batch, or role=student."""
    visible = Q(target_type="all") | Q(target_type="role", target_value="student")
    if batch_id:
        visible |= Q(target_type="batch", target_value=str(batch_id))
    return (
        Announcement.objects.filter(branch_id=branch_id, is_active=True)
        .filter(visible)
        .select_related("branch")
        .order_by("-created_at")
    )


def list_for_faculty(branch_id, faculty_user_id=None):
    """Announcements a faculty member should see:
      - everyone, or role=faculty/staff, plus
      - batch-targeted announcements for any class where they are the class teacher.
    """
    from apps.academics.models import Batch

    visible = (
        Q(target_type="all")
        | Q(target_type="role", target_value__in=["faculty", "staff"])
    )
    if faculty_user_id:
        teacher_batch_ids = [
            str(bid) for bid in Batch.objects.filter(
                course__department__branch_id=branch_id,
                class_teacher_id=faculty_user_id, is_active=True,
            ).values_list("id", flat=True)
        ]
        if teacher_batch_ids:
            visible |= Q(target_type="batch", target_value__in=teacher_batch_ids)

    return (
        Announcement.objects.filter(branch_id=branch_id, is_active=True)
        .filter(visible)
        .select_related("branch")
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
