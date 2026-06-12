"""Views — marks entry for faculty and admin."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.examinations.interactors import marks as marks_i
from apps.examinations.permissions import IsFacultyOrAdmin
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import marks as marks_q
from apps.examinations.serializers.marks import (
    BulkSaveMarksSerializer,
    MarksEntrySerializer,
    PatchMarksSerializer,
    RosterStudentSerializer,
    SubmitMarksSerializer,
)


class ScheduleSlotRosterView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request, slot_id) -> Response:
        branch = resolve_branch(request)
        slot = exam_q.get_schedule_slot_in_branch(branch.pk, slot_id)
        if not slot:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        roster = marks_i.get_slot_roster(slot, branch_id=branch.pk)
        return Response({"roster": RosterStudentSerializer(roster, many=True).data})


class ScheduleSlotMarksView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request, slot_id) -> Response:
        branch = resolve_branch(request)
        slot = exam_q.get_schedule_slot_in_branch(branch.pk, slot_id)
        if not slot:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        entries = marks_q.list_marks_for_slot_by_exam_subject(
            slot.exam_id, slot.subject_id, slot.batch_id
        )
        payload = [marks_i.serialize_marks_entry(e, slot) for e in entries]
        return Response({"entries": MarksEntrySerializer(payload, many=True).data})

    def post(self, request, slot_id) -> Response:
        branch = resolve_branch(request)
        slot = exam_q.get_schedule_slot_in_branch(branch.pk, slot_id)
        if not slot:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = BulkSaveMarksSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        saved = marks_i.bulk_save_draft_marks(
            slot,
            branch_id=branch.pk,
            entries=data["entries"],
            actor=request.user,
            override=data.get("override", False),
            override_reason=data.get("overrideReason", ""),
        )
        return Response({"entries": MarksEntrySerializer(saved, many=True).data})


class ScheduleSlotMarksSubmitView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def post(self, request, slot_id) -> Response:
        branch = resolve_branch(request)
        slot = exam_q.get_schedule_slot_in_branch(branch.pk, slot_id)
        if not slot:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = SubmitMarksSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        count = marks_i.submit_slot_marks(
            slot,
            actor=request.user,
            override=data.get("override", False),
            override_reason=data.get("overrideReason", ""),
        )
        return Response({"submittedCount": count})


class MarksEntryDetailView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def patch(self, request, marks_id) -> Response:
        branch = resolve_branch(request)
        entry = marks_q.get_marks_entry(branch.pk, marks_id)
        if not entry:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        slot = exam_q.get_schedule_slot_for_marks_entry(entry)
        if not slot:
            return Response({"error": "Schedule slot not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = PatchMarksSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        updated = marks_i.patch_marks_entry(
            entry,
            slot,
            branch_id=branch.pk,
            marks_raw=data.get("marks"),
            is_absent=data.get("isAbsent", False),
            expected_version=data["version"],
            actor=request.user,
            override=data.get("override", False),
            override_reason=data.get("overrideReason", ""),
        )
        return Response({"entry": MarksEntrySerializer(updated).data})

