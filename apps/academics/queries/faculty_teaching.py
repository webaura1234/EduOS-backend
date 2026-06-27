"""Queries — faculty homeroom (class teacher) and subject-teaching scope."""

from __future__ import annotations

from apps.academics.models import Batch, BatchFaculty


def _batch_label(batch: Batch) -> str:
    if batch.course_id:
        return f"{batch.course.name} - {batch.name}"
    return batch.name


def homeroom_batches(branch_id, faculty_id):
    """Active batches where faculty is the class teacher."""
    return list(
        Batch.objects.filter(
            course__department__branch_id=branch_id,
            class_teacher_id=faculty_id,
            is_active=True,
        ).select_related("course")
        .order_by("course__name", "name")
    )


def is_homeroom_teacher(branch_id, faculty_id, batch_id) -> bool:
    return Batch.objects.filter(
        course__department__branch_id=branch_id,
        pk=batch_id,
        class_teacher_id=faculty_id,
        is_active=True,
    ).exists()


def subject_teaching_assignments(branch_id, faculty_id):
    """One row per (batch, subject) from active BatchFaculty assignments."""
    rows = (
        BatchFaculty.objects.filter(
            faculty_id=faculty_id,
            is_active=True,
            batch_subject__batch__course__department__branch_id=branch_id,
            batch_subject__batch__is_active=True,
        )
        .select_related(
            "batch_subject__subject",
            "batch_subject__batch",
            "batch_subject__batch__course",
        )
        .order_by(
            "batch_subject__batch__course__name",
            "batch_subject__batch__name",
            "batch_subject__subject__name",
        )
    )
    seen: set[tuple] = set()
    out = []
    for r in rows:
        batch = r.batch_subject.batch
        subject = r.batch_subject.subject
        key = (batch.id, subject.id)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "batch": batch,
            "subject": subject,
            "batch_label": _batch_label(batch),
            "subject_name": subject.name,
        })
    return out


def subject_teaching_batch_ids(branch_id, faculty_id) -> set:
    return {a["batch"].id for a in subject_teaching_assignments(branch_id, faculty_id)}


def faculty_teaches_batch_subject(branch_id, faculty_id, batch_id, subject_id) -> bool:
    return BatchFaculty.objects.filter(
        faculty_id=faculty_id,
        is_active=True,
        batch_subject__batch_id=batch_id,
        batch_subject__subject_id=subject_id,
        batch_subject__batch__course__department__branch_id=branch_id,
    ).exists()


def teaching_classes_grouped(branch_id, faculty_id) -> list[dict]:
    """Grouped by batch with subject list — matches FacultyTeachingClass shape."""
    by_batch: dict = {}
    for row in subject_teaching_assignments(branch_id, faculty_id):
        batch = row["batch"]
        bid = batch.id
        if bid not in by_batch:
            by_batch[bid] = {
                "classSectionId": str(bid),
                "classLabel": row["batch_label"],
                "subjects": [],
            }
        subj = row["subject"]
        subjects = by_batch[bid]["subjects"]
        sid = str(subj.id)
        if not any(s["id"] == sid for s in subjects):
            subjects.append({"id": sid, "name": row["subject_name"]})
    return list(by_batch.values())


def homerooms_payload(batches) -> list[dict]:
    return [
        {"classSectionId": str(b.id), "classLabel": _batch_label(b)}
        for b in batches
    ]
