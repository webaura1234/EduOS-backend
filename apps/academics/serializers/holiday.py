"""Serializers — Holiday calendar."""

from rest_framework import serializers

from apps.academics.models import HolidayType


class HolidaySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    date = serializers.DateField(read_only=True)
    name = serializers.CharField(read_only=True)
    holidayType = serializers.CharField(source="holiday_type", read_only=True)
    appliesTo = serializers.JSONField(source="applies_to", read_only=True)
    version = serializers.IntegerField(read_only=True)


class CreateHolidaySerializer(serializers.Serializer):
    date = serializers.DateField()
    name = serializers.CharField(max_length=150)
    holidayType = serializers.ChoiceField(
        choices=HolidayType.values, required=False, default=HolidayType.PUBLIC
    )
    appliesTo = serializers.JSONField(required=False)


class UpdateHolidaySerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    name = serializers.CharField(max_length=150, required=False)
    holidayType = serializers.ChoiceField(choices=HolidayType.values, required=False)
    appliesTo = serializers.JSONField(required=False)
    version = serializers.IntegerField(required=False)
