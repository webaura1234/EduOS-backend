"""Resolve homework batches to the academic year students actually use."""

from __future__ import annotations

from apps.academics.models import Batch
from apps.academics.queries import calendar as cal_q


def resolve_homework_target_batch(
    batch: Batch | None,
    branch_id,
    *,
    allow_create: bool = False,
) -> Batch | None:
    """Map a batch to the current academic year's equivalent class section."""
    if batch is None:
        return None
    current = cal_q.get_current_year(branch_id)
    if current is None or batch.academic_year_id == current.pk:
        return batch
    mapped = (
        Batch.objects.filter(
            course__department__branch_id=branch_id,
            academic_year_id=current.pk,
            course__name=batch.course.name,
            name=batch.name,
            is_active=True,
        )
        .select_related("course", "course__department__branch", "academic_year")
        .order_by("-created_at")
        .first()
    )
    if mapped:
        return mapped
    if allow_create and current:
        created, _ = Batch.objects.get_or_create(
            course=batch.course,
            academic_year=current,
            name=batch.name,
            defaults=dict(capacity=getattr(batch, "capacity", None) or 40),
        )
        return created
    return batch


def sibling_batch_ids(batch: Batch | None, branch_id) -> list:
    """All batch rows for the same class section in a branch (includes prior academic years)."""
    if batch is None:
        return []
    return list(
        Batch.objects.filter(
            course__department__branch_id=branch_id,
            course__name=batch.course.name,
            name=batch.name,
            is_active=True,
        ).values_list("pk", flat=True)
    )
