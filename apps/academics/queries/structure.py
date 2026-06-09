"""
Queries — Department, Course, Batch (academic hierarchy). Branch-scoped via joins.
"""

from apps.academics.models import Batch, Course, Department


# ── Department ────────────────────────────────────────────────────────────────
def list_departments(branch_id):
    return Department.objects.filter(branch_id=branch_id).order_by("name")


def get_department(branch_id, dept_id) -> Department | None:
    try:
        return Department.objects.get(branch_id=branch_id, pk=dept_id)
    except (Department.DoesNotExist, ValueError, TypeError):
        return None


def department_name_exists(branch_id, name) -> bool:
    return Department.objects.filter(branch_id=branch_id, name__iexact=name).exists()


def create_department(branch_id, *, name, code="", department_type, head_faculty_id=None) -> Department:
    return Department.objects.create(
        branch_id=branch_id, name=name, code=code,
        department_type=department_type, head_faculty_id=head_faculty_id,
    )


def update_department(dept: Department, fields: dict) -> Department:
    for k, v in fields.items():
        setattr(dept, k, v)
    if fields:
        dept.save(update_fields=list(fields.keys()))
    return dept


# ── Course ────────────────────────────────────────────────────────────────────
def list_courses(branch_id, department_id=None):
    qs = Course.objects.filter(department__branch_id=branch_id).select_related("department")
    if department_id:
        qs = qs.filter(department_id=department_id)
    return qs.order_by("name")


def get_course(branch_id, course_id) -> Course | None:
    try:
        return Course.objects.select_related("department").get(
            department__branch_id=branch_id, pk=course_id
        )
    except (Course.DoesNotExist, ValueError, TypeError):
        return None


def create_course(*, department, name, code="", duration_years=1, regulation="", total_credits=None) -> Course:
    return Course.objects.create(
        department=department, name=name, code=code, duration_years=duration_years,
        regulation=regulation, total_credits=total_credits,
    )


def update_course(course: Course, fields: dict) -> Course:
    for k, v in fields.items():
        setattr(course, k, v)
    if fields:
        course.save(update_fields=list(fields.keys()))
    return course


# ── Batch ─────────────────────────────────────────────────────────────────────
def list_batches(branch_id, *, course_id=None, academic_year_id=None):
    qs = Batch.objects.filter(course__department__branch_id=branch_id).select_related(
        "course", "academic_year"
    )
    if course_id:
        qs = qs.filter(course_id=course_id)
    if academic_year_id:
        qs = qs.filter(academic_year_id=academic_year_id)
    return qs.order_by("name")


def get_batch(branch_id, batch_id) -> Batch | None:
    try:
        return Batch.objects.select_related("course", "academic_year").get(
            course__department__branch_id=branch_id, pk=batch_id
        )
    except (Batch.DoesNotExist, ValueError, TypeError):
        return None


def create_batch(*, course, academic_year, name, capacity=40, class_teacher_id=None) -> Batch:
    return Batch.objects.create(
        course=course, academic_year=academic_year, name=name,
        capacity=capacity, class_teacher_id=class_teacher_id,
    )


def update_batch(batch: Batch, fields: dict) -> Batch:
    for k, v in fields.items():
        setattr(batch, k, v)
    if fields:
        batch.save(update_fields=list(fields.keys()))
    return batch
