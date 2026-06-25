"""Syllabus units — definition, section-scoped progress, faculty assignments."""

from django.utils import timezone

from apps.academics.models import BatchFaculty, BatchSubject, SyllabusUnit, SyllabusUnitProgress


def unit_dict(u) -> dict:
    return {"id": str(u.id), "title": u.title, "order": u.order}


def completion_stats(units, completed_ids: set[str]) -> tuple[int, list[str]]:
    total = len(units)
    done = [str(u.id) for u in units if str(u.id) in completed_ids]
    percent = round(len(done) / total * 100) if total else 0
    return percent, done


def faculty_assignments(branch_id, faculty_user_id):
    """One row per (batch, subject) the faculty is assigned to teach."""
    rows = (
        BatchFaculty.objects.filter(
            faculty_id=faculty_user_id, is_active=True,
            batch_subject__batch__course__department__branch_id=branch_id,
        )
        .select_related(
            "batch_subject__subject", "batch_subject__subject__course",
            "batch_subject__batch", "batch_subject__batch__course",
        )
        .order_by("batch_subject__subject__name", "batch_subject__batch__name")
    )
    return [
        {"subject": r.batch_subject.subject, "batch": r.batch_subject.batch}
        for r in rows
    ]


def units_for_subject(branch_id, subject_id):
    return SyllabusUnit.objects.filter(
        branch_id=branch_id, subject_id=subject_id, is_active=True,
    ).order_by("order", "created_at")


def units_by_subject(branch_id, subject_ids):
    """Bulk: {subject_id: [SyllabusUnit, ...]} for the given subjects."""
    units = SyllabusUnit.objects.filter(
        branch_id=branch_id, subject_id__in=subject_ids, is_active=True,
    ).order_by("order", "created_at")
    grouped: dict = {sid: [] for sid in subject_ids}
    for u in units:
        grouped.setdefault(u.subject_id, []).append(u)
    return grouped


def get_unit(branch_id, unit_id) -> SyllabusUnit | None:
    try:
        return SyllabusUnit.objects.get(branch_id=branch_id, pk=unit_id, is_active=True)
    except (SyllabusUnit.DoesNotExist, ValueError, TypeError):
        return None


def next_order(branch_id, subject_id) -> int:
    last = (
        SyllabusUnit.objects.filter(branch_id=branch_id, subject_id=subject_id, is_active=True)
        .order_by("-order").first()
    )
    return (last.order + 1) if last else 1


def create_unit(*, branch, subject, title, order=None, user=None) -> SyllabusUnit:
    if order is None:
        order = next_order(branch.pk, subject.pk)
    return SyllabusUnit.objects.create(
        branch=branch, subject=subject, title=title, order=order,
        created_by=user, updated_by=user,
    )


def update_unit(unit: SyllabusUnit, *, title=None, order=None, user=None) -> SyllabusUnit:
    fields = ["updated_by", "updated_at"]
    if title is not None:
        unit.title = title
        fields.append("title")
    if order is not None:
        unit.order = order
        fields.append("order")
    unit.updated_by = user
    unit.save(update_fields=fields)
    return unit


def delete_unit(unit: SyllabusUnit, user=None) -> None:
    unit.is_active = False
    unit.updated_by = user
    unit.save(update_fields=["is_active", "updated_by", "updated_at"])
    _delete_progress_for_units([unit.pk])


def _delete_progress_for_units(unit_ids) -> None:
    if unit_ids:
        SyllabusUnitProgress.objects.filter(unit_id__in=unit_ids).delete()


def sync_units_for_subject(branch, subject, payloads, user=None) -> list[SyllabusUnit]:
    """Reconcile syllabus units from the admin form (create / update / soft-delete)."""
    cleaned = [
        {"id": p.get("id"), "title": (p.get("title") or "").strip()}
        for p in (payloads or [])
        if (p.get("title") or "").strip()
    ]
    existing = {str(u.id): u for u in units_for_subject(branch.pk, subject.pk)}
    kept: set[str] = set()
    for i, p in enumerate(cleaned):
        order = i + 1
        uid = p.get("id")
        if uid and str(uid) in existing:
            u = existing[str(uid)]
            if u.subject_id != subject.pk:
                raise ValueError("Syllabus unit does not belong to this subject.")
            update_unit(u, title=p["title"], order=order, user=user)
            kept.add(str(uid))
        else:
            u = create_unit(branch=branch, subject=subject, title=p["title"], order=order, user=user)
            kept.add(str(u.id))
    removed_ids = []
    for uid, u in existing.items():
        if uid not in kept:
            delete_unit(u, user=user)
            removed_ids.append(u.pk)
    return list(units_for_subject(branch.pk, subject.pk))


def batch_teaches_subject(branch_id, batch_id, subject_id) -> bool:
    return BatchSubject.objects.filter(
        batch_id=batch_id,
        subject_id=subject_id,
        is_active=True,
        batch__course__department__branch_id=branch_id,
    ).exists()


def faculty_teaches(branch_id, faculty_user_id, batch_id, subject_id) -> bool:
    return BatchFaculty.objects.filter(
        faculty_id=faculty_user_id, is_active=True,
        batch_subject__batch_id=batch_id,
        batch_subject__subject_id=subject_id,
        batch_subject__batch__course__department__branch_id=branch_id,
    ).exists()


def batches_by_subject(branch_id, subject_ids) -> dict:
    """{subject_id: [batch, ...]} for active BatchSubject rows."""
    rows = BatchSubject.objects.filter(
        subject_id__in=subject_ids, is_active=True,
        batch__course__department__branch_id=branch_id,
    ).select_related("batch", "batch__course")
    grouped: dict = {sid: [] for sid in subject_ids}
    seen: dict = {}
    for bs in rows:
        key = (bs.subject_id, bs.batch_id)
        if key in seen:
            continue
        seen[key] = True
        grouped.setdefault(bs.subject_id, []).append(bs.batch)
    return grouped


def progress_for_batches(branch_id, batch_ids, subject_ids) -> dict:
    """{batch_id: {subject_id: set(unit_id_str)}}"""
    if not batch_ids or not subject_ids:
        return {}
    rows = SyllabusUnitProgress.objects.filter(
        branch_id=branch_id,
        batch_id__in=batch_ids,
        unit__subject_id__in=subject_ids,
        is_active=True,
    ).values_list("batch_id", "unit__subject_id", "unit_id")
    result: dict = {}
    for batch_id, subject_id, unit_id in rows:
        result.setdefault(batch_id, {}).setdefault(subject_id, set()).add(str(unit_id))
    return result


def completed_ids_for_batch(branch_id, batch_id, subject_id) -> set[str]:
    rows = SyllabusUnitProgress.objects.filter(
        branch_id=branch_id,
        batch_id=batch_id,
        unit__subject_id=subject_id,
        is_active=True,
    ).values_list("unit_id", flat=True)
    return {str(uid) for uid in rows}


def set_completion(branch_id, batch_id, subject_id, completed_unit_ids, user=None) -> list[SyllabusUnit]:
    """Mark units complete/incomplete for one class section + subject."""
    if not batch_teaches_subject(branch_id, batch_id, subject_id):
        raise ValueError("This subject is not offered in the selected class section.")
    units = list(units_for_subject(branch_id, subject_id))
    valid = {str(u.id) for u in units}
    completed = {str(x) for x in (completed_unit_ids or [])} & valid
    unit_pks = [u.pk for u in units]
    now = timezone.now()

    SyllabusUnitProgress.objects.filter(
        batch_id=batch_id, unit_id__in=unit_pks,
    ).exclude(unit_id__in=[u.pk for u in units if str(u.id) in completed]).delete()

    for u in units:
        if str(u.id) in completed:
            SyllabusUnitProgress.objects.update_or_create(
                batch_id=batch_id,
                unit_id=u.pk,
                defaults={
                    "branch_id": branch_id,
                    "completed_at": now,
                    "completed_by": user,
                    "created_by": user,
                    "updated_by": user,
                    "is_active": True,
                },
            )
    return units


def payload_for_assignment(*, subject, batch, units, completed_ids: set[str], class_label: str) -> dict:
    percent, done = completion_stats(units, completed_ids)
    return {
        "id": str(subject.id),
        "batchId": str(batch.id),
        "name": subject.name,
        "code": subject.code or "",
        "classLabel": class_label,
        "syllabusCompletionPercent": percent,
        "syllabusUnits": [unit_dict(u) for u in units],
        "completedUnitIds": done,
    }
