"""Interactors — Department, Course, Batch."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.academics.helpers import check_version, get_faculty_user, reject_class_teacher_for_college
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import timetable as tt_q


def _batch_year_frozen(batch) -> None:
    if batch.academic_year.is_frozen:
        raise ValidationError("The academic year for this batch is frozen.")


@transaction.atomic
def create_department(branch_id, tenant_id, *, name, code, department_type, head_faculty_id=None, user=None):
    if struct_q.department_name_exists(branch_id, name):
        raise ValidationError({"name": "A department with this name already exists."})
    head_id = None
    if head_faculty_id:
        faculty = get_faculty_user(tenant_id, head_faculty_id)
        if not faculty:
            raise ValidationError({"headFacultyId": "Faculty not found."})
        head_id = faculty.pk
    return struct_q.create_department(
        branch_id, name=name, code=code, department_type=department_type,
        head_faculty_id=head_id, user=user,
    )


@transaction.atomic
def update_department(dept, tenant_id, *, fields: dict, user=None):
    check_version(dept, fields.pop("version", None))
    name = fields.get("name", dept.name)
    if struct_q.department_name_exists(dept.branch_id, name, exclude_id=dept.pk):
        raise ValidationError({"name": "A department with this name already exists."})
    if "head_faculty_id" in fields:
        hf = fields["head_faculty_id"]
        if hf:
            faculty = get_faculty_user(tenant_id, hf)
            if not faculty:
                raise ValidationError({"headFacultyId": "Faculty not found."})
            fields["head_faculty_id"] = faculty.pk
        else:
            fields["head_faculty_id"] = None
    return struct_q.update_department(dept, fields, user=user)


@transaction.atomic
def delete_department(dept, user=None):
    return struct_q.soft_delete_department(dept, user=user)


@transaction.atomic
def create_course(department, *, name, code, duration_years, regulation, total_credits, user=None):
    if struct_q.course_name_exists(department.pk, name):
        raise ValidationError({"name": "A course with this name already exists in this department."})
    return struct_q.create_course(
        department=department, name=name, code=code, duration_years=duration_years,
        regulation=regulation, total_credits=total_credits, user=user,
    )


@transaction.atomic
def update_course(course, *, fields: dict, user=None):
    check_version(course, fields.pop("version", None))
    name = fields.get("name", course.name)
    if struct_q.course_name_exists(course.department_id, name, exclude_id=course.pk):
        raise ValidationError({"name": "A course with this name already exists."})
    return struct_q.update_course(course, fields, user=user)


@transaction.atomic
def delete_course(course, user=None):
    return struct_q.soft_delete_course(course, user=user)


@transaction.atomic
def create_batch(tenant, course, academic_year, *, name, capacity, class_teacher_id=None, user=None):
    if academic_year.is_frozen:
        raise ValidationError("Cannot create batches in a frozen academic year.")
    if struct_q.batch_name_exists(course.pk, academic_year.pk, name):
        raise ValidationError({"name": "A batch with this name already exists for this course and year."})
    teacher_id = None
    if class_teacher_id:
        reject_class_teacher_for_college(tenant)
        faculty = get_faculty_user(tenant.pk, class_teacher_id)
        if not faculty:
            raise ValidationError({"classTeacherId": "Faculty not found."})
        teacher_id = faculty.pk
    return struct_q.create_batch(
        course=course, academic_year=academic_year, name=name,
        capacity=capacity, class_teacher_id=teacher_id, user=user,
    )


@transaction.atomic
def update_batch(tenant, batch, *, fields: dict, user=None):
    _batch_year_frozen(batch)
    check_version(batch, fields.pop("version", None))
    name = fields.get("name", batch.name)
    if struct_q.batch_name_exists(batch.course_id, batch.academic_year_id, name, exclude_id=batch.pk):
        raise ValidationError({"name": "A batch with this name already exists."})
    if "class_teacher_id" in fields:
        ct = fields["class_teacher_id"]
        if ct:
            reject_class_teacher_for_college(tenant)
            faculty = get_faculty_user(tenant.pk, ct)
            if not faculty:
                raise ValidationError({"classTeacherId": "Faculty not found."})
            fields["class_teacher_id"] = faculty.pk
    return struct_q.update_batch(batch, fields, user=user)


@transaction.atomic
def delete_batch(batch, user=None):
    _batch_year_frozen(batch)
    if struct_q.batch_has_students(batch.pk):
        raise ValidationError("Cannot delete a batch that has enrolled students.")
    from apps.academics.queries import timetable as tt_q

    if tt_q.batch_has_active_timetable_entries(batch.pk):
        raise ValidationError("Cannot delete a batch with active timetable entries.")
    return struct_q.soft_delete_batch(batch, user=user)
