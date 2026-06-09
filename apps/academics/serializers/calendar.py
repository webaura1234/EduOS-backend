"""Serializers — AcademicYear and AcademicPeriod (camelCase I/O)."""

from rest_framework import serializers

from apps.academics.models import PeriodType


class AcademicYearSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    startDate = serializers.DateField(source="start_date", read_only=True)
    endDate = serializers.DateField(source="end_date", read_only=True)
    isCurrent = serializers.BooleanField(source="is_current", read_only=True)
    isFrozen = serializers.BooleanField(source="is_frozen", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)


class CreateAcademicYearSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=20)
    startDate = serializers.DateField()
    endDate = serializers.DateField()
    isCurrent = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if attrs["endDate"] <= attrs["startDate"]:
            raise serializers.ValidationError({"endDate": "End date must be after start date."})
        return attrs


class AcademicPeriodSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    academicYearId = serializers.UUIDField(source="academic_year_id", read_only=True)
    periodType = serializers.CharField(source="period_type", read_only=True)
    sequence = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    startDate = serializers.DateField(source="start_date", read_only=True)
    endDate = serializers.DateField(source="end_date", read_only=True)


class CreateAcademicPeriodSerializer(serializers.Serializer):
    periodType = serializers.ChoiceField(choices=PeriodType.values)
    sequence = serializers.IntegerField(min_value=1)
    name = serializers.CharField(max_length=50)
    startDate = serializers.DateField()
    endDate = serializers.DateField()
