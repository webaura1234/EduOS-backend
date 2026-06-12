"""Interactors — assignment create/list, student submit, faculty grade."""

from __future__ import annotations

import base64
import binascii
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import structure as struct_q
from apps.admissions.queries import enrollment as enrollment_q
from apps.examinations.enums import AssignmentStatus, SubmissionStatus
from apps.examinations.helpers import validate_marks_against_max
from apps.examinations.queries import assignment as asg_q
from apps.examinations.services.assignment_files import (
    attachment_name_from_key,
    store_submission_file,
    submission_file_key,
)


def _similarity_status(score) -> str:
    if score is None:
        return "ok"
    value = float(score)
    if value >= 70:
        return "high"
    if value >= 30:
        return "warning"
    return "ok"


def serialize_assignment(assignment) -> dict:
    bs = assignment.batch_subject
    return {
        "id": str(assignment.pk),
        "title": assignment.title,
        "description": assignment.description,
        "classSectionId": str(bs.batch_id),
        "classLabel": bs.batch.name,
        "subjectId": str(bs.subject_id),
        "subjectName": bs.subject.name,
        "dueAt": assignment.due_at.isoformat(),
        "maxMarks": float(assignment.max_marks),
        "status": assignment.status,
        "createdAt": assignment.created_at.isoformat(),
        "createdByUserId": str(assignment.created_by_id) if assignment.created_by_id else "",
    }


def serialize_submission(submission) -> dict:
    return {
        "id": str(submission.pk),
        "assignmentId": str(submission.assignment_id),
        "studentId": str(submission.student.student_profile_id),
        "studentName": submission.student.user.full_name,
        "submittedAt": submission.updated_at.isoformat(),
        "attachmentName": attachment_name_from_key(submission.file_key),
        "gradedMarks": float(submission.graded_marks) if submission.graded_marks is not None else None,
        "similarityPercent": float(submission.plagiarism_score or 0),
        "similarityStatus": _similarity_status(submission.plagiarism_score),
        "submissionStatus": submission.submission_status,
    }


def _resolve_batch_subject(branch_id, *, batch_id, subject_id, academic_period_id=None):
    batch = struct_q.get_batch(branch_id, batch_id)
    if not batch:
        raise ValidationError({"classSectionId": "Batch not found in this branch."})
    subject = curr_q.get_subject(branch_id, subject_id)
    if not subject:
        raise ValidationError({"subjectId": "Subject not found in this branch."})

    qs = curr_q.list_batch_subjects(
        branch_id,
        batch_id=batch_id,
        academic_period_id=academic_period_id,
    )
    for bs in qs:
        if str(bs.subject_id) == str(subject_id):
            return bs
    raise ValidationError({"batchSubject": "Subject is not offered to this batch for the selected period."})


def _parse_due_at(raw) -> timezone.datetime:
    if hasattr(raw, "isoformat"):
        dt = raw
    else:
        dt = parse_datetime(str(raw))
    if dt is None:
        raise ValidationError({"dueAt": "Invalid datetime."})
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _decode_file_content(raw: str) -> bytes:
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError({"fileContent": "File content must be valid base64."}) from exc


@transaction.atomic
def list_assignments_data(*, branch_id, batch_id=None, subject_id=None):
    asg_q.close_past_due_assignments(branch_id)
    assignments = list(asg_q.list_assignments(branch_id, batch_id=batch_id, subject_id=subject_id))
    submissions = list(asg_q.list_submissions_for_branch(branch_id))
    return {
        "assignments": [serialize_assignment(a) for a in assignments],
        "submissions": [serialize_submission(s) for s in submissions],
    }


@transaction.atomic
def create_assignment(
    *,
    branch_id,
    title,
    description,
    batch_id,
    subject_id,
    due_at_raw,
    max_marks,
    actor,
    academic_period_id=None,
) -> dict:
    batch_subject = _resolve_batch_subject(
        branch_id,
        batch_id=batch_id,
        subject_id=subject_id,
        academic_period_id=academic_period_id,
    )
    due_at = _parse_due_at(due_at_raw)
    if due_at <= timezone.now():
        raise ValidationError({"dueAt": "Due date must be in the future."})

    assignment = asg_q.create_assignment(
        branch_id=branch_id,
        batch_subject_id=batch_subject.pk,
        title=title.strip(),
        description=(description or "").strip(),
        max_marks=max_marks,
        due_at=due_at,
        created_by=actor,
        user=actor,
    )
    return serialize_assignment(assignment)


@transaction.atomic
def submit_assignment(
    assignment,
    *,
    student_profile,
    file_name: str,
    file_content: str,
    actor,
) -> dict:
    if assignment.status == AssignmentStatus.CLOSED:
        raise ValidationError({"assignment": "This assignment is closed."})

    batch_id = assignment.batch_subject.batch_id
    if str(student_profile.current_batch_id) != str(batch_id):
        raise PermissionDenied("You are not enrolled in the class for this assignment.")

    # Enrollment seam (Stage 5): submissions key off StudentEnrollment.
    enrollment = enrollment_q.resolve_enrollment_for_profile(
        student_profile, batch=assignment.batch_subject.batch
    )
    if not enrollment:
        raise PermissionDenied("You are not enrolled in the class for this assignment.")

    existing = asg_q.get_submission_for_student(assignment.pk, enrollment.pk)
    if existing and existing.submission_status == SubmissionStatus.GRADED:
        raise ValidationError({"submission": "Graded submissions cannot be replaced."})

    content_bytes = _decode_file_content(file_content)
    if not file_name.strip():
        raise ValidationError({"fileName": "File name is required."})

    file_key = submission_file_key(
        branch_id=assignment.branch_id,
        assignment_id=assignment.pk,
        student_id=student_profile.pk,
        file_name=file_name.strip(),
    )
    store_submission_file(key=file_key, content_bytes=content_bytes)

    now = timezone.now()
    submission_status = SubmissionStatus.LATE if now > assignment.due_at else SubmissionStatus.SUBMITTED
    submission = asg_q.upsert_submission(
        assignment_id=assignment.pk,
        student_id=enrollment.pk,
        file_key=file_key,
        submission_status=submission_status,
        plagiarism_score=Decimal("0"),
        user=actor,
    )
    payload = serialize_submission(submission)
    payload["fileKey"] = file_key
    return payload


@transaction.atomic
def grade_submission(
    submission,
    *,
    graded_marks_raw,
    actor,
) -> dict:
    assignment = submission.assignment
    try:
        marks = Decimal(str(graded_marks_raw))
    except Exception as exc:
        raise ValidationError({"gradedMarks": "Graded marks must be a number."}) from exc

    validate_marks_against_max(marks, max_marks=assignment.max_marks, is_absent=False)
    updated = asg_q.grade_submission(submission, graded_marks=marks, user=actor)
    return serialize_submission(updated)
