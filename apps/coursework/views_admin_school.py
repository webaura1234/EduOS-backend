"""Admin Class & diary overview — class teachers, homework, dropdown options."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.helpers import batch_display_label
from apps.academics.models import Batch
from apps.academics.scoping import resolve_branch
from apps.accounts.models.user import Role, User
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.coursework import queries as hw_q


def _homework_entry(h) -> dict:
    label = batch_display_label(h.batch) if h.batch_id else ""
    return {
        "id": str(h.id),
        "classSectionId": str(h.batch_id),
        "classLabel": label,
        "date": h.date.isoformat(),
        "title": h.title,
        "details": h.details,
        "status": h.status,
        "createdBy": h.created_by.full_name if h.created_by_id else "",
        "createdAt": h.created_at.isoformat(),
        "publishedAt": h.published_at.isoformat() if h.published_at else None,
    }


class AdminSchoolOverviewView(APIView):
    """GET → SchoolOnlyData aggregate for the admin Class & diary screen."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        tenant = branch.tenant

        batches = list(
            Batch.objects.filter(
                course__department__branch_id=branch.pk,
                is_active=True,
            )
            .select_related("course", "course__department", "class_teacher")
            .order_by("course__name", "name")
        )

        class_teachers = []
        class_sections = []
        for b in batches:
            label = batch_display_label(b)
            class_sections.append({
                "id": str(b.id),
                "label": label,
                "departmentId": str(b.course.department_id),
                "courseId": str(b.course_id),
                "grade": b.course.name,
                "section": b.name,
                "academicYearId": str(b.academic_year_id),
            })
            if b.class_teacher_id:
                class_teachers.append({
                    "classSectionId": str(b.id),
                    "classLabel": label,
                    "teacherUserId": str(b.class_teacher_id),
                    "teacherName": b.class_teacher.full_name,
                    "assignedAt": b.updated_at.isoformat(),
                })

        faculty_options = [
            {"id": str(u.id), "name": u.full_name}
            for u in User.objects.filter(
                tenant_id=tenant.id,
                branch_id=branch.pk,
                role=Role.FACULTY,
                is_active=True,
            ).order_by("first_name", "last_name")
        ]

        homework = [_homework_entry(h) for h in hw_q.list_for_branch(branch.pk)]

        return Response({
            "institutionType": tenant.institution_type,
            "classTeachers": class_teachers,
            "homework": homework,
            "activities": [],
            "participation": [],
            "ptm": [],
            "classSections": class_sections,
            "facultyOptions": faculty_options,
        })
