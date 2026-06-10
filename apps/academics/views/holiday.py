"""Views — Holiday calendar."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.interactors import holiday as hol_i
from apps.academics.permissions import IsAdminOrSuperAdmin
from apps.academics.queries import holiday as hol_q
from apps.academics.scoping import resolve_branch
from apps.academics.serializers.holiday import (
    CreateHolidaySerializer,
    HolidaySerializer,
    UpdateHolidaySerializer,
)
from apps.academics.views.structure import _map_fields


class HolidayListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        holidays = hol_q.list_holidays(
            branch.pk,
            from_date=request.query_params.get("from"),
            to_date=request.query_params.get("to"),
        )
        return Response({"holidays": HolidaySerializer(holidays, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = CreateHolidaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        holiday = hol_i.create_holiday(
            branch.pk, date=data["date"], name=data["name"],
            holiday_type=data.get("holidayType", "public"),
            applies_to=data.get("appliesTo"), user=request.user,
        )
        return Response({"holiday": HolidaySerializer(holiday).data}, status=status.HTTP_201_CREATED)


class HolidayDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, holiday_id) -> Response:
        branch = resolve_branch(request)
        holiday = hol_q.get_holiday(branch.pk, holiday_id)
        if not holiday:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateHolidaySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = _map_fields(data, {
            "date": "date", "name": "name", "holidayType": "holiday_type",
            "appliesTo": "applies_to", "version": "version",
        })
        holiday = hol_i.update_holiday(holiday, fields=fields, user=request.user)
        return Response({"holiday": HolidaySerializer(holiday).data})

    def delete(self, request, holiday_id) -> Response:
        branch = resolve_branch(request)
        holiday = hol_q.get_holiday(branch.pk, holiday_id)
        if not holiday:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        hol_i.delete_holiday(holiday, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
