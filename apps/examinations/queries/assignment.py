"""Queries — assignments and submissions (all ORM here)."""

from django.utils import timezone

from apps.examinations.enums import AssignmentStatus, SubmissionStatus
from apps.examinations.models import Assignment, AssignmentSubmission

_ASSIGNMENT_SELECT = (
    "batch_subject",
    "batch_subject__batch",
    "batch_subject__subject",
    "batch_subject__academic_period",
    "created_by",
)


def _assignment_qs(branch_id):
    return (
        Assignment.objects.filter(branch_id=branch_id, is_active=True)
        .select_related(*_ASSIGNMENT_SELECT)
        .order_by("-due_at")
    )


def list_assignments(branch_id, *, batch_id=None, subject_id=None, status=None):
    qs = _assignment_qs(branch_id)
    if batch_id:
        qs = qs.filter(batch_subject__batch_id=batch_id)
    if subject_id:
        qs = qs.filter(batch_subject__subject_id=subject_id)
    if status:
        qs = qs.filter(status=status)
    return qs


def list_assignments_for_batches(branch_id, batch_ids):
    if not batch_ids:
        return _assignment_qs(branch_id).none()
    return _assignment_qs(branch_id).filter(batch_subject__batch_id__in=batch_ids)


def list_assignments_created_by_faculty_in_batches(branch_id, faculty_id, batch_ids):
    if not batch_ids:
        return _assignment_qs(branch_id).none()
    return _assignment_qs(branch_id).filter(
        created_by_id=faculty_id,
        batch_subject__batch_id__in=batch_ids,
    )


def get_assignment(branch_id, assignment_id) -> Assignment | None:
    try:
        return Assignment.objects.select_related(*_ASSIGNMENT_SELECT).get(
            branch_id=branch_id, pk=assignment_id, is_active=True,
        )
    except (Assignment.DoesNotExist, ValueError, TypeError):
        return None


def create_assignment(
    *,
    branch_id,
    batch_subject_id,
    title,
    description,
    max_marks,
    due_at,
    created_by,
    user=None,
) -> Assignment:
    return Assignment.objects.create(
        branch_id=branch_id,
        batch_subject_id=batch_subject_id,
        title=title,
        description=description,
        max_marks=max_marks,
        due_at=due_at,
        status=AssignmentStatus.OPEN,
        created_by=created_by,
        updated_by=user,
    )


def update_assignment(assignment: Assignment, fields: dict, user=None) -> Assignment:
    for k, v in fields.items():
        setattr(assignment, k, v)
    if fields:
        assignment.version += 1
        if user:
            assignment.updated_by = user
        assignment.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return assignment


def list_submissions_for_branch(branch_id, *, assignment_id=None):
    qs = (
        AssignmentSubmission.objects.filter(
            assignment__branch_id=branch_id,
            is_active=True,
        )
        .select_related(
            "assignment",
            "student",
            "student__student_profile__user",
            "student__batch",
        )
        .order_by("-updated_at")
    )
    if assignment_id:
        qs = qs.filter(assignment_id=assignment_id)
    return qs


def list_submissions_for_assignments(branch_id, assignment_ids):
    if not assignment_ids:
        return AssignmentSubmission.objects.none()
    return list_submissions_for_branch(branch_id).filter(assignment_id__in=assignment_ids)


def get_submission(branch_id, submission_id) -> AssignmentSubmission | None:
    try:
        return AssignmentSubmission.objects.select_related(
            "assignment",
            "assignment__batch_subject",
            "assignment__batch_subject__batch",
            "student",
            "student__student_profile__user",
        ).get(
            assignment__branch_id=branch_id,
            pk=submission_id,
            is_active=True,
        )
    except (AssignmentSubmission.DoesNotExist, ValueError, TypeError):
        return None


def get_submission_for_student(assignment_id, student_id) -> AssignmentSubmission | None:
    try:
        return AssignmentSubmission.objects.select_related(
            "assignment", "student", "student__student_profile__user",
        ).get(
            assignment_id=assignment_id,
            student_id=student_id,
            is_active=True,
        )
    except (AssignmentSubmission.DoesNotExist, ValueError, TypeError):
        return None


def upsert_submission(
    *,
    assignment_id,
    student_id,
    file_key,
    submission_status,
    plagiarism_score=None,
    user=None,
) -> AssignmentSubmission:
    submission, created = AssignmentSubmission.objects.get_or_create(
        assignment_id=assignment_id,
        student_id=student_id,
        defaults={
            "file_key": file_key,
            "submission_status": submission_status,
            "plagiarism_score": plagiarism_score,
            "created_by": user,
            "updated_by": user,
        },
    )
    if not created:
        submission.file_key = file_key
        submission.submission_status = submission_status
        submission.plagiarism_score = plagiarism_score
        submission.graded_marks = None
        submission.version += 1
        if user:
            submission.updated_by = user
        submission.save(
            update_fields=[
                "file_key",
                "submission_status",
                "plagiarism_score",
                "graded_marks",
                "version",
                "updated_by",
                "updated_at",
            ]
        )
    return submission


def grade_submission(
    submission: AssignmentSubmission,
    *,
    graded_marks,
    user=None,
) -> AssignmentSubmission:
    submission.graded_marks = graded_marks
    submission.submission_status = SubmissionStatus.GRADED
    submission.version += 1
    if user:
        submission.updated_by = user
    submission.save(
        update_fields=["graded_marks", "submission_status", "version", "updated_by", "updated_at"]
    )
    return submission


def close_past_due_assignments(branch_id) -> int:
    now = timezone.now()
    return Assignment.objects.filter(
        branch_id=branch_id,
        status=AssignmentStatus.OPEN,
        due_at__lt=now,
        is_active=True,
    ).update(status=AssignmentStatus.CLOSED, updated_at=now)
