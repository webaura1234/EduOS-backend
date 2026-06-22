"""Syllabus units — faculty-facing reads + completion updates."""

from django.utils import timezone

from apps.academics.models import BatchFaculty, SyllabusUnit


def faculty_subjects(branch_id, faculty_user_id):
    """Distinct subjects a faculty teaches, each with the class labels it's taught in.

    Returns a list of dicts: {subject, class_labels: [str, ...]} preserving a stable order.
    """
    rows = (
        BatchFaculty.objects.filter(
            faculty_id=faculty_user_id, is_active=True,
            batch_subject__batch__course__department__branch_id=branch_id,
        )
        .select_related("batch_subject__subject", "batch_subject__batch")
        .order_by("batch_subject__subject__name")
    )
    out: dict = {}
    for r in rows:
        bs = r.batch_subject
        subj = bs.subject
        entry = out.setdefault(subj.id, {"subject": subj, "class_labels": []})
        label = bs.batch.name if bs.batch_id else None
        if label and label not in entry["class_labels"]:
            entry["class_labels"].append(label)
    return list(out.values())


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


def set_completion(branch_id, subject_id, completed_unit_ids, user=None):
    """Mark the given units complete and the rest of the subject's units incomplete."""
    completed = {str(x) for x in (completed_unit_ids or [])}
    units = list(units_for_subject(branch_id, subject_id))
    now = timezone.now()
    for u in units:
        should = str(u.id) in completed
        if should and not u.is_completed:
            u.is_completed = True
            u.completed_at = now
            u.completed_by = user
            u.save(update_fields=["is_completed", "completed_at", "completed_by", "updated_at"])
        elif not should and u.is_completed:
            u.is_completed = False
            u.completed_at = None
            u.completed_by = None
            u.save(update_fields=["is_completed", "completed_at", "completed_by", "updated_at"])
    return units
