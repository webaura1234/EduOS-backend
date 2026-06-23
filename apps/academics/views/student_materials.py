"""Student-facing study materials — materials for the logged-in student's batch."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import admin_extras as extra_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsStudent
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile


def _material(m) -> dict:
    label = ""
    if m.batch_id:
        label = (f"{m.batch.course.name} - {m.batch.name}"
                 if m.batch.course_id else m.batch.name)
    return {
        "id": str(m.id),
        "classSectionId": str(m.batch_id) if m.batch_id else "",
        "classLabel": label,
        "fileName": m.file_name,
        "s3Key": m.s3_key,
        "url": m.url,
        "uploadedAt": m.created_at.isoformat(),
        "uploadedByUserId": str(m.uploaded_by_id) if m.uploaded_by_id else "",
        "unitTitles": [],
    }


class StudentStudyMaterialsView(APIView):
    """GET → { materials } for the logged-in student's current batch (F-179)."""
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        profile = getattr(request.user, "student_profile", None)
        if not profile:
            return Response({"materials": []})
        enrollment = get_active_enrollment_for_profile(profile.pk)
        if not enrollment or not enrollment.batch_id:
            return Response({"materials": []})

        materials = extra_q.list_materials_for_batch(branch.pk, enrollment.batch_id)
        return Response({"materials": [_material(m) for m in materials]})
