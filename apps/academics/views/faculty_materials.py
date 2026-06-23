"""Faculty-facing study materials — read-only view of materials for the classes
they teach. Uploads are admin-only; faculty can only view."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import Batch
from apps.academics.queries import admin_extras as extra_q
from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.attendance.permissions import IsFacultyOrAdmin


def _assigned_batch_ids(branch_id, faculty_id):
    """Classes the faculty is responsible for: class-teacher + timetable-taught."""
    ids = set(
        Batch.objects.filter(
            course__department__branch_id=branch_id,
            class_teacher_id=faculty_id, is_active=True,
        ).values_list("id", flat=True)
    )
    for e in tt_q.list_active_entries_for_branch(branch_id):
        if e.faculty_id == faculty_id and e.timetable_id:
            ids.add(e.timetable.batch_id)
    return ids


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
    }


class FacultyStudyMaterialsView(APIView):
    """GET → { materials } for the faculty's classes (read-only)."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        batch_ids = _assigned_batch_ids(branch.pk, request.user.pk)
        materials = extra_q.list_materials_for_batches(branch.pk, batch_ids)
        return Response({"materials": [_material(m) for m in materials]})
