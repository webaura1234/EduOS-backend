"""Views — PeriodSlot, Room, Timetable, TimetableEntry."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.interactors import timetable as tt_i
from apps.academics.permissions import IsAdminOrSuperAdmin
from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.academics.serializers.timetable import (
    CreatePeriodSlotSerializer,
    CreateRoomSerializer,
    CreateTimetableEntrySerializer,
    CreateTimetableSerializer,
    PeriodSlotSerializer,
    RoomSerializer,
    TimetableActionSerializer,
    TimetableEntrySerializer,
    TimetableSerializer,
    UpdatePeriodSlotSerializer,
    UpdateRoomSerializer,
    UpdateTimetableEntrySerializer,
)
from apps.academics.views.structure import _map_fields


class PeriodSlotListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        slots = tt_q.list_period_slots(branch.pk)
        return Response({"periodSlots": PeriodSlotSerializer(slots, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = CreatePeriodSlotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        slot = tt_i.create_period_slot(
            branch.pk, name=data["name"], sequence=data["sequence"],
            start_time=data["startTime"], end_time=data["endTime"], user=request.user,
        )
        return Response({"periodSlot": PeriodSlotSerializer(slot).data}, status=status.HTTP_201_CREATED)


class PeriodSlotDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, slot_id) -> Response:
        branch = resolve_branch(request)
        slot = tt_q.get_period_slot(branch.pk, slot_id)
        if not slot:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdatePeriodSlotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = _map_fields(data, {
            "name": "name", "sequence": "sequence",
            "startTime": "start_time", "endTime": "end_time", "version": "version",
        })
        slot = tt_i.update_period_slot(slot, fields=fields, user=request.user)
        return Response({"periodSlot": PeriodSlotSerializer(slot).data})

    def delete(self, request, slot_id) -> Response:
        branch = resolve_branch(request)
        slot = tt_q.get_period_slot(branch.pk, slot_id)
        if not slot:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        tt_i.delete_period_slot(slot, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        rooms = tt_q.list_rooms(branch.pk)
        return Response({"rooms": RoomSerializer(rooms, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = CreateRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        room = tt_i.create_room(
            branch.pk, name=data["name"], code=data.get("code", ""),
            capacity=data.get("capacity", 40), is_lab=data.get("isLab", False),
            user=request.user,
        )
        return Response({"room": RoomSerializer(room).data}, status=status.HTTP_201_CREATED)


class RoomDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, room_id) -> Response:
        branch = resolve_branch(request)
        room = tt_q.get_room(branch.pk, room_id)
        if not room:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = _map_fields(data, {
            "name": "name", "code": "code", "capacity": "capacity",
            "isLab": "is_lab", "version": "version",
        })
        room = tt_i.update_room(room, fields=fields, user=request.user)
        return Response({"room": RoomSerializer(room).data})

    def delete(self, request, room_id) -> Response:
        branch = resolve_branch(request)
        room = tt_q.get_room(branch.pk, room_id)
        if not room:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        tt_i.delete_room(room, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TimetableListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        timetables = tt_q.list_timetables(
            branch.pk,
            batch_id=request.query_params.get("batchId"),
            academic_period_id=request.query_params.get("academicPeriodId"),
        )
        return Response({"timetables": TimetableSerializer(timetables, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = CreateTimetableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tt = tt_i.create_timetable(
            branch.pk,
            batch_id=data["batchId"],
            academic_period_id=data["academicPeriodId"],
            user=request.user,
        )
        return Response({"timetable": TimetableSerializer(tt).data}, status=status.HTTP_201_CREATED)


class TimetableDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, timetable_id) -> Response:
        branch = resolve_branch(request)
        tt = tt_q.get_timetable(branch.pk, timetable_id)
        if not tt:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        entries = tt_q.list_timetable_entries(tt.pk)
        return Response({
            "timetable": TimetableSerializer(tt).data,
            "entries": TimetableEntrySerializer(entries, many=True).data,
        })


class TimetableEntryListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, timetable_id) -> Response:
        branch = resolve_branch(request)
        tt = tt_q.get_timetable(branch.pk, timetable_id)
        if not tt:
            return Response({"error": "Timetable not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CreateTimetableEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        entry = tt_i.create_timetable_entry(
            branch.pk, request.user.tenant_id, tt,
            batch_subject_id=data["batchSubjectId"],
            period_slot_id=data["periodSlotId"],
            day_of_week=int(data["dayOfWeek"]),
            faculty_id=data.get("facultyId"),
            room_id=data.get("roomId"),
            status=data.get("status", "active"),
            user=request.user,
        )
        return Response({"entry": TimetableEntrySerializer(entry).data}, status=status.HTTP_201_CREATED)


class TimetableEntryDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, entry_id) -> Response:
        branch = resolve_branch(request)
        entry = tt_q.get_timetable_entry(branch.pk, entry_id)
        if not entry:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateTimetableEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = _map_fields(data, {
            "batchSubjectId": "batch_subject_id",
            "periodSlotId": "period_slot_id",
            "dayOfWeek": "day_of_week",
            "facultyId": "faculty_id",
            "roomId": "room_id",
            "status": "status",
            "version": "version",
        })
        if "day_of_week" in fields:
            fields["day_of_week"] = int(fields["day_of_week"])
        entry = tt_i.update_timetable_entry(
            branch.pk, request.user.tenant_id, entry, fields=fields, user=request.user,
        )
        return Response({"entry": TimetableEntrySerializer(entry).data})

    def delete(self, request, entry_id) -> Response:
        branch = resolve_branch(request)
        entry = tt_q.get_timetable_entry(branch.pk, entry_id)
        if not entry:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        tt_i.delete_timetable_entry(entry, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TimetableClashesView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        clashes = tt_i.list_all_clashes(branch.pk)
        return Response({"clashes": [c.to_dict() for c in clashes]})


class TimetableActionsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request) -> Response:
        branch = resolve_branch(request)
        serializer = TimetableActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tt = tt_q.get_timetable(branch.pk, data["timetableId"])
        if not tt:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if data["action"] == "publish":
            tt = tt_i.publish_timetable(tt, user=request.user)
        return Response({"timetable": TimetableSerializer(tt).data})
