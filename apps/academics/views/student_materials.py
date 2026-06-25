"""Student-facing study materials — materials for the logged-in student's batch."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.interactors.study_materials import group_materials
from apps.academics.queries import admin_extras as extra_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsStudent
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile


class StudentStudyMaterialsView(APIView):
    """GET → grouped folders + general materials for the student's batch (F-179)."""
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        profile = getattr(request.user, "student_profile", None)
        if not profile:
            return Response({"folders": [], "general": []})
        enrollment = get_active_enrollment_for_profile(profile.pk)
        if not enrollment or not enrollment.batch_id:
            return Response({"folders": [], "general": []})

        materials = list(extra_q.list_materials_for_batch(branch.pk, enrollment.batch_id))
        return Response(group_materials(materials))
