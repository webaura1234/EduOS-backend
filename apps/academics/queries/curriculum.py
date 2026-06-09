"""
Queries — Subject (course curriculum). Branch-scoped via course → department.
"""

from apps.academics.models import Subject


def list_subjects(branch_id, course_id=None):
    qs = Subject.objects.filter(course__department__branch_id=branch_id).select_related("course")
    if course_id:
        qs = qs.filter(course_id=course_id)
    return qs.order_by("name")


def get_subject(branch_id, subject_id) -> Subject | None:
    try:
        return Subject.objects.select_related("course").get(
            course__department__branch_id=branch_id, pk=subject_id
        )
    except (Subject.DoesNotExist, ValueError, TypeError):
        return None


def subject_code_exists(course_id, code) -> bool:
    return bool(code) and Subject.objects.filter(course_id=course_id, code__iexact=code).exists()


def create_subject(*, course, name, code="", subject_type, max_marks=100,
                   pass_marks=35, credits=None, is_elective=False) -> Subject:
    return Subject.objects.create(
        course=course, name=name, code=code, subject_type=subject_type,
        max_marks=max_marks, pass_marks=pass_marks, credits=credits, is_elective=is_elective,
    )


def update_subject(subject: Subject, fields: dict) -> Subject:
    for k, v in fields.items():
        setattr(subject, k, v)
    if fields:
        subject.save(update_fields=list(fields.keys()))
    return subject
