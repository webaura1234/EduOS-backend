"""Interactors — Subject, BatchSubject, BatchFaculty."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.academics.helpers import check_version, get_faculty_user, require_credits_for_college
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import structure as struct_q


@transaction.atomic
def create_subject(tenant, course, *, name, code, subject_type, max_marks, pass_marks, credits, is_elective, user=None):
    require_credits_for_college(tenant, credits)
    if curr_q.subject_code_exists(course.pk, code):
        raise ValidationError({"code": "A subject with this code already exists in this course."})
    return curr_q.create_subject(
        course=course, name=name, code=code, subject_type=subject_type,
        max_marks=max_marks, pass_marks=pass_marks, credits=credits, is_elective=is_elective, user=user,
    )


@transaction.atomic
def update_subject(tenant, subject, *, fields: dict, user=None):
    check_version(subject, fields.pop("version", None))
    if "credits" in fields:
        require_credits_for_college(tenant, fields["credits"])
    code = fields.get("code", subject.code)
    if curr_q.subject_code_exists(subject.course_id, code, exclude_id=subject.pk):
        raise ValidationError({"code": "A subject with this code already exists."})
    return curr_q.update_subject(subject, fields, user=user)


class SubjectHasMarksError(Exception):
    """Raised when subject delete is blocked by existing marks."""


@transaction.atomic
def delete_subject(subject, user=None):
    if curr_q.subject_has_marks(subject.pk):
        raise SubjectHasMarksError()
    affected = curr_q.mark_subject_timetable_entries_tbd(subject.pk, user=user)
    curr_q.soft_delete_subject(subject, user=user)
    return {"affectedEntryIds": affected}


@transaction.atomic
def create_batch_subject(batch, subject, academic_period, *, is_required=True, user=None):
    if batch.academic_year_id != academic_period.academic_year_id:
        raise ValidationError("Academic period must belong to the batch's academic year.")
    if batch.academic_year.is_frozen:
        raise ValidationError("Cannot modify curriculum in a frozen academic year.")
    if curr_q.batch_subject_exists(batch.pk, subject.pk, academic_period.pk):
        raise ValidationError("This subject is already assigned to the batch for this period.")
    return curr_q.create_batch_subject(
        batch=batch, subject=subject, academic_period=academic_period,
        is_required=is_required, user=user,
    )


@transaction.atomic
def update_batch_subject(bs, *, fields: dict, user=None):
    if bs.batch.academic_year.is_frozen:
        raise ValidationError("Cannot modify curriculum in a frozen academic year.")
    check_version(bs, fields.pop("version", None))
    return curr_q.update_batch_subject(bs, fields, user=user)


@transaction.atomic
def delete_batch_subject(bs, user=None):
    if bs.batch.academic_year.is_frozen:
        raise ValidationError("Cannot modify curriculum in a frozen academic year.")
    return curr_q.soft_delete_batch_subject(bs, user=user)


@transaction.atomic
def create_batch_faculty(tenant_id, batch_subject, *, faculty_id, role, assigned_at, ended_at=None, user=None):
    if batch_subject.batch.academic_year.is_frozen:
        raise ValidationError("Cannot modify faculty assignments in a frozen academic year.")
    faculty = get_faculty_user(tenant_id, faculty_id)
    if not faculty:
        raise ValidationError({"facultyId": "Faculty not found."})
    return curr_q.create_batch_faculty(
        batch_subject=batch_subject, faculty=faculty, role=role,
        assigned_at=assigned_at, ended_at=ended_at, user=user,
    )


@transaction.atomic
def update_batch_faculty(assignment, *, fields: dict, user=None):
    if assignment.batch_subject.batch.academic_year.is_frozen:
        raise ValidationError("Cannot modify faculty assignments in a frozen academic year.")
    check_version(assignment, fields.pop("version", None))
    return curr_q.update_batch_faculty(assignment, fields, user=user)


@transaction.atomic
def delete_batch_faculty(assignment, user=None):
    if assignment.batch_subject.batch.academic_year.is_frozen:
        raise ValidationError("Cannot modify faculty assignments in a frozen academic year.")
    return curr_q.soft_delete_batch_faculty(assignment, user=user)
