"""Queries — Homework reads/writes."""

from django.utils import timezone

from apps.coursework.models import Homework


def list_for_faculty(branch_id, faculty_user_id):
    return (
        Homework.objects.filter(branch_id=branch_id, created_by_id=faculty_user_id, is_active=True)
        .select_related("batch", "batch__course", "created_by")
        .order_by("-date", "-created_at")
    )


def list_for_branch(branch_id):
    return (
        Homework.objects.filter(branch_id=branch_id, is_active=True)
        .select_related("batch", "batch__course", "created_by")
        .order_by("-date", "-created_at")
    )


def list_published_for_batch(branch_id, batch_id):
    return (
        Homework.objects.filter(
            branch_id=branch_id, batch_id=batch_id, status="published", is_active=True,
        )
        .select_related("batch", "created_by")
        .order_by("-date")
    )


def get_in_branch(branch_id, homework_id) -> Homework | None:
    try:
        return Homework.objects.select_related("batch", "created_by").get(
            branch_id=branch_id, pk=homework_id, is_active=True,
        )
    except (Homework.DoesNotExist, ValueError, TypeError):
        return None


def create(*, branch, batch, date, title, details, publish, user=None) -> Homework:
    return Homework.objects.create(
        branch=branch, batch=batch, date=date, title=title, details=details,
        status="published" if publish else "draft",
        published_at=timezone.now() if publish else None,
        created_by=user, updated_by=user,
    )


def update(hw: Homework, *, batch, date, title, details, publish, user=None) -> Homework:
    hw.batch = batch
    hw.date = date
    hw.title = title
    hw.details = details
    if publish and hw.status != "published":
        hw.status = "published"
        hw.published_at = timezone.now()
    hw.updated_by = user
    hw.save(update_fields=["batch", "date", "title", "details", "status",
                           "published_at", "updated_by", "updated_at"])
    return hw


def soft_delete(hw: Homework, user=None) -> None:
    hw.is_active = False
    hw.updated_by = user
    hw.save(update_fields=["is_active", "updated_by", "updated_at"])
