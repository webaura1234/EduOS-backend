"""
Queries — Department, Course, Batch (academic hierarchy). Branch-scoped via joins.
"""

from apps.academics.models import Batch, Course, Department
from apps.accounts.models.profile import StudentProfile


def list_departments(branch_id):
    return Department.objects.filter(branch_id=branch_id, is_active=True).order_by("name")


def get_department(branch_id, dept_id) -> Department | None:
    try:
        return Department.objects.get(branch_id=branch_id, pk=dept_id, is_active=True)
    except (Department.DoesNotExist, ValueError, TypeError):
        return None


def department_name_exists(branch_id, name, exclude_id=None) -> bool:
    qs = Department.objects.filter(branch_id=branch_id, name__iexact=name, is_active=True)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def create_department(branch_id, *, name, code="", department_type, head_faculty_id=None, user=None) -> Department:
    return Department.objects.create(
        branch_id=branch_id,
        name=name,
        code=code,
        department_type=department_type,
        head_faculty_id=head_faculty_id,
        created_by=user,
        updated_by=user,
    )


def update_department(dept: Department, fields: dict, user=None) -> Department:
    for k, v in fields.items():
        setattr(dept, k, v)
    if fields:
        dept.version += 1
        if user:
            dept.updated_by = user
        dept.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return dept


def soft_delete_department(dept: Department, user=None) -> Department:
    dept.soft_delete(user)
    dept.version += 1
    dept.save(update_fields=["version", "updated_at"])
    return dept


def list_courses(branch_id, department_id=None):
    qs = Course.objects.filter(department__branch_id=branch_id, is_active=True).select_related("department")
    if department_id:
        qs = qs.filter(department_id=department_id)
    return qs.order_by("name")


def get_course(branch_id, course_id) -> Course | None:
    try:
        return Course.objects.select_related("department").get(
            department__branch_id=branch_id, pk=course_id, is_active=True
        )
    except (Course.DoesNotExist, ValueError, TypeError):
        return None


def get_course_by_name(branch_id, name) -> Course | None:
    normalized = (name or "").strip()
    if not normalized:
        return None
    return (
        Course.objects.filter(
            department__branch_id=branch_id, is_active=True, name__iexact=normalized,
        )
        .select_related("department")
        .first()
    )


def course_name_exists(department_id, name, exclude_id=None) -> bool:
    qs = Course.objects.filter(department_id=department_id, name__iexact=name, is_active=True)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def get_or_create_course_in_department(department, name, user=None):
    """School grade (or college program) — find or create under a stream/department."""
    clean = (name or "").strip()
    if not clean:
        raise ValueError("Course name is required")
    existing = (
        Course.objects.filter(department_id=department.pk, is_active=True, name__iexact=clean)
        .first()
    )
    if existing:
        return existing
    return create_course(department=department, name=clean, user=user)


def department_has_active_courses(department_id) -> bool:
    return Course.objects.filter(department_id=department_id, is_active=True).exists()


def create_course(*, department, name, code="", duration_years=1, regulation="", total_credits=None, user=None) -> Course:
    return Course.objects.create(
        department=department,
        name=name,
        code=code,
        duration_years=duration_years,
        regulation=regulation,
        total_credits=total_credits,
        created_by=user,
        updated_by=user,
    )


def update_course(course: Course, fields: dict, user=None) -> Course:
    for k, v in fields.items():
        setattr(course, k, v)
    if fields:
        course.version += 1
        if user:
            course.updated_by = user
        course.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return course


def soft_delete_course(course: Course, user=None) -> Course:
    course.soft_delete(user)
    course.version += 1
    course.save(update_fields=["version", "updated_at"])
    return course


def list_batches(branch_id, *, course_id=None, academic_year_id=None):
    qs = Batch.objects.filter(course__department__branch_id=branch_id, is_active=True).select_related(
        "course", "course__department", "academic_year"
    )
    if course_id:
        qs = qs.filter(course_id=course_id)
    if academic_year_id:
        qs = qs.filter(academic_year_id=academic_year_id)
    return qs.order_by("name")


def get_batch(branch_id, batch_id) -> Batch | None:
    try:
        return Batch.objects.select_related(
            "course", "course__department", "academic_year", "class_teacher",
        ).get(
            course__department__branch_id=branch_id, pk=batch_id, is_active=True
        )
    except (Batch.DoesNotExist, ValueError, TypeError):
        return None


def batch_name_exists(course_id, academic_year_id, name, exclude_id=None) -> bool:
    qs = Batch.objects.filter(
        course_id=course_id, academic_year_id=academic_year_id, name__iexact=name, is_active=True
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def batch_has_students(batch_id) -> bool:
    return StudentProfile.objects.filter(current_batch_id=batch_id, is_active=True).exists()


def batch_has_study_materials(batch_id) -> bool:
    from apps.academics.models import StudyMaterial
    return StudyMaterial.objects.filter(batch_id=batch_id, is_active=True).exists()


def create_batch(*, course, academic_year, name, capacity=40, class_teacher_id=None, user=None) -> Batch:
    return Batch.objects.create(
        course=course,
        academic_year=academic_year,
        name=name,
        capacity=capacity,
        class_teacher_id=class_teacher_id,
        created_by=user,
        updated_by=user,
    )


def update_batch(batch: Batch, fields: dict, user=None) -> Batch:
    for k, v in fields.items():
        setattr(batch, k, v)
    if fields:
        batch.version += 1
        if user:
            batch.updated_by = user
        batch.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return batch


def soft_delete_batch(batch: Batch, user=None) -> Batch:
    batch.soft_delete(user)
    batch.version += 1
    batch.save(update_fields=["version", "updated_at"])
    return batch


def list_courses_in_department_ordered(department_id):
    return Course.objects.filter(department_id=department_id, is_active=True).order_by("name")
