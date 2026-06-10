"""Views — AcademicYear and AcademicPeriod."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.interactors import calendar as cal_i
from apps.academics.permissions import IsAdminOrSuperAdmin
from apps.academics.queries import calendar as cal_q
from apps.academics.scoping import resolve_branch
from apps.academics.serializers.calendar import (
    AcademicPeriodSerializer,
    AcademicYearActionSerializer,
    AcademicYearSerializer,
    CreateAcademicPeriodSerializer,
    CreateAcademicYearSerializer,
    UpdateAcademicPeriodSerializer,
    UpdateAcademicYearSerializer,
)


class AcademicYearListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        years = cal_q.list_years(branch.pk)
        return Response({"academicYears": AcademicYearSerializer(years, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = CreateAcademicYearSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        year = cal_i.create_academic_year(
            branch.pk,
            name=data["name"],
            start_date=data["startDate"],
            end_date=data["endDate"],
            is_current=data.get("isCurrent", False),
            user=request.user,
        )
        return Response({"academicYear": AcademicYearSerializer(year).data}, status=status.HTTP_201_CREATED)


class AcademicYearDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, year_id) -> Response:
        branch = resolve_branch(request)
        year = cal_q.get_year(branch.pk, year_id)
        if not year:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"academicYear": AcademicYearSerializer(year).data})

    def patch(self, request, year_id) -> Response:
        branch = resolve_branch(request)
        year = cal_q.get_year(branch.pk, year_id)
        if not year:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateAcademicYearSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = {}
        if "name" in data:
            fields["name"] = data["name"]
        if "startDate" in data:
            fields["start_date"] = data["startDate"]
        if "endDate" in data:
            fields["end_date"] = data["endDate"]
        if "version" in data:
            fields["version"] = data["version"]
        year = cal_i.update_academic_year(year, fields=fields, user=request.user)
        return Response({"academicYear": AcademicYearSerializer(year).data})


class AcademicYearActionsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request) -> Response:
        branch = resolve_branch(request)
        serializer = AcademicYearActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        year = cal_q.get_year(branch.pk, data["yearId"])
        if not year:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if "version" in data:
            from apps.academics.helpers import check_version

            check_version(year, data["version"])
        year = cal_i.academic_year_action(year=year, action=data["action"], user=request.user)
        return Response({"academicYear": AcademicYearSerializer(year).data})


class AcademicPeriodListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, year_id) -> Response:
        branch = resolve_branch(request)
        year = cal_q.get_year(branch.pk, year_id)
        if not year:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        periods = cal_q.list_periods(year.pk)
        return Response({"periods": AcademicPeriodSerializer(periods, many=True).data})

    def post(self, request, year_id) -> Response:
        branch = resolve_branch(request)
        year = cal_q.get_year(branch.pk, year_id)
        if not year:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CreateAcademicPeriodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        period = cal_i.create_academic_period(
            year,
            period_type=data["periodType"],
            sequence=data["sequence"],
            name=data["name"],
            start_date=data["startDate"],
            end_date=data["endDate"],
            user=request.user,
        )
        return Response({"period": AcademicPeriodSerializer(period).data}, status=status.HTTP_201_CREATED)


class AcademicPeriodDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, year_id, period_id) -> Response:
        branch = resolve_branch(request)
        year = cal_q.get_year(branch.pk, year_id)
        if not year:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        period = cal_q.get_period(year.pk, period_id)
        if not period:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateAcademicPeriodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = {}
        mapping = {
            "periodType": "period_type",
            "sequence": "sequence",
            "name": "name",
            "startDate": "start_date",
            "endDate": "end_date",
            "version": "version",
        }
        for src, dst in mapping.items():
            if src in data:
                fields[dst] = data[src]
        period = cal_i.update_academic_period(period, year, fields=fields, user=request.user)
        return Response({"period": AcademicPeriodSerializer(period).data})

    def delete(self, request, year_id, period_id) -> Response:
        branch = resolve_branch(request)
        year = cal_q.get_year(branch.pk, year_id)
        if not year:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        period = cal_q.get_period(year.pk, period_id)
        if not period:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        cal_i.delete_academic_period(period, year, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
