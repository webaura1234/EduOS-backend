"""Queries — result publication, student results, publish locking (all ORM here)."""

from django.db.models import F
from django.utils import timezone

from apps.examinations.enums import MarksStatus, ResultStatus
from apps.examinations.models import (
    Exam,
    GradeScale,
    MarksEntry,
    ResultPublication,
    ResultRevisionHistory,
    StudentResult,
)


def get_grade_scale_for_course(branch_id, course_id) -> GradeScale | None:
    scale = GradeScale.objects.filter(
        branch_id=branch_id,
        course_id=course_id,
        is_default=True,
        is_active=True,
    ).first()
    if scale:
        return scale
    return GradeScale.objects.filter(
        branch_id=branch_id,
        course_id=course_id,
        is_active=True,
    ).first()


def lock_exam_for_publish(exam_id) -> Exam | None:
    try:
        return Exam.objects.select_for_update().get(pk=exam_id, is_active=True)
    except (Exam.DoesNotExist, ValueError, TypeError):
        return None


def set_exam_publish_in_progress(exam: Exam, in_progress: bool, user=None) -> Exam:
    exam.publish_in_progress = in_progress
    exam.version += 1
    if user:
        exam.updated_by = user
    exam.save(update_fields=["publish_in_progress", "version", "updated_by", "updated_at"])
    return exam


def update_exam_publication_state(
    exam: Exam,
    *,
    is_published: bool,
    result_status: str,
    user=None,
) -> Exam:
    exam.is_published = is_published
    exam.result_status = result_status
    exam.version += 1
    if user:
        exam.updated_by = user
    exam.save(update_fields=["is_published", "result_status", "version", "updated_by", "updated_at"])
    return exam


def count_unsubmitted_marks_for_exam(exam_id) -> int:
    return MarksEntry.objects.filter(
        exam_id=exam_id,
        marks_status=MarksStatus.DRAFT,
        is_active=True,
    ).count()


def list_submitted_marks_with_subjects(exam_id):
    return MarksEntry.objects.filter(
        exam_id=exam_id,
        marks_status__in=[MarksStatus.SUBMITTED, MarksStatus.LOCKED],
        is_active=True,
    ).select_related(
        "student",
        "student__student_profile__user",
        "student__batch",
        "student__batch__course",
        "subject",
    )


def lock_marks_for_exam(exam_id, user=None) -> int:
    now = timezone.now()
    return MarksEntry.objects.filter(
        exam_id=exam_id,
        marks_status=MarksStatus.SUBMITTED,
        is_active=True,
    ).update(
        marks_status=MarksStatus.LOCKED,
        version=F("version") + 1,
        updated_by=user,
        updated_at=now,
    )


def apply_grace_to_marks_entry(
    *,
    exam_id,
    subject_id,
    student_id,
    grace_amount,
    user=None,
) -> MarksEntry | None:
    try:
        entry = MarksEntry.objects.get(
            exam_id=exam_id,
            subject_id=subject_id,
            student_id=student_id,
            is_active=True,
        )
    except (MarksEntry.DoesNotExist, ValueError, TypeError):
        return None
    entry.grace_applied = grace_amount
    entry.version += 1
    if user:
        entry.updated_by = user
    entry.save(update_fields=["grace_applied", "version", "updated_by", "updated_at"])
    return entry


def get_current_publication(exam_id) -> ResultPublication | None:
    return (
        ResultPublication.objects.filter(exam_id=exam_id, is_current=True, is_active=True)
        .select_related("published_by")
        .first()
    )


def list_publications_for_exam(exam_id):
    return (
        ResultPublication.objects.filter(exam_id=exam_id, is_active=True)
        .select_related("published_by")
        .order_by("-revision_no")
    )


def get_publication_note(publication_id) -> str:
    row = (
        ResultRevisionHistory.objects.filter(publication_id=publication_id, is_active=True)
        .order_by("-created_at")
        .first()
    )
    return row.change_summary if row else ""


def create_publication(
    *,
    exam_id,
    published_at,
    published_by,
    snapshot_hash: str,
    revision_no: int = 1,
    parent_publication_id=None,
    user=None,
) -> ResultPublication:
    return ResultPublication.objects.create(
        exam_id=exam_id,
        published_at=published_at,
        published_by=published_by,
        snapshot_hash=snapshot_hash,
        revision_no=revision_no,
        parent_publication_id=parent_publication_id,
        is_current=True,
        is_revised=False,
        created_by=user,
        updated_by=user,
    )


def supersede_publication(publication: ResultPublication, user=None) -> ResultPublication:
    publication.is_current = False
    publication.is_revised = True
    publication.version += 1
    if user:
        publication.updated_by = user
    publication.save(update_fields=["is_current", "is_revised", "version", "updated_by", "updated_at"])
    return publication


def create_revision_history(
    *,
    publication_id,
    changed_by,
    change_summary: str,
    field_changes: dict,
    previous_snapshot_hash: str,
    new_snapshot_hash: str,
    user=None,
) -> ResultRevisionHistory:
    return ResultRevisionHistory.objects.create(
        publication_id=publication_id,
        changed_by=changed_by,
        change_summary=change_summary,
        field_changes=field_changes,
        previous_snapshot_hash=previous_snapshot_hash,
        new_snapshot_hash=new_snapshot_hash,
        created_by=user,
        updated_by=user,
    )


def upsert_student_result(
    *,
    exam_id,
    student_id,
    publication_id,
    total_marks,
    percentage,
    grade: str,
    gpa,
    is_pass: bool,
    arrear_subjects: list,
    report_card_key: str = "",
    marksheet_key: str = "",
    user=None,
) -> StudentResult:
    result, _created = StudentResult.objects.update_or_create(
        exam_id=exam_id,
        student_id=student_id,
        defaults={
            "publication_id": publication_id,
            "total_marks": total_marks,
            "percentage": percentage,
            "grade": grade,
            "gpa": gpa,
            "is_pass": is_pass,
            "arrear_subjects": arrear_subjects,
            "report_card_key": report_card_key,
            "marksheet_key": marksheet_key,
            "updated_by": user,
        },
    )
    if _created and user:
        result.created_by = user
        result.save(update_fields=["created_by"])
    return result


def list_student_results(exam_id):
    return StudentResult.objects.filter(exam_id=exam_id, is_active=True).select_related(
        "student",
        "student__student_profile__user",
        "student__batch",
        "publication",
    )


def get_student_result(exam_id, student_id) -> StudentResult | None:
    try:
        return StudentResult.objects.select_related("student", "student__student_profile__user").get(
            exam_id=exam_id,
            student_id=student_id,
            is_active=True,
        )
    except (StudentResult.DoesNotExist, ValueError, TypeError):
        return None


def delete_publication(publication_id) -> int:
    """Hard delete — interactor must block for published/current records (EC-EXAM-03)."""
    deleted, _ = ResultPublication.objects.filter(pk=publication_id).delete()
    return deleted
