"""Serializers — seating plans and invigilator assignments (camelCase)."""

from rest_framework import serializers


class SeatingAllocationSerializer(serializers.Serializer):
    roomId = serializers.CharField()
    roomName = serializers.CharField()
    seats = serializers.ListField(child=serializers.DictField())


class SeatingPlanSerializer(serializers.Serializer):
    examSlotId = serializers.CharField()
    generatedAt = serializers.CharField()
    totalStudents = serializers.IntegerField()
    allocations = SeatingAllocationSerializer(many=True)
    note = serializers.CharField()


class GenerateSeatingSerializer(serializers.Serializer):
    examSlotId = serializers.UUIDField(required=False)
    roomIds = serializers.ListField(child=serializers.UUIDField(), required=False)


class InvigilationAssignmentSerializer(serializers.Serializer):
    examSlotId = serializers.CharField()
    facultyId = serializers.CharField()
    facultyName = serializers.CharField()
    assignedAt = serializers.CharField()
    assignedBy = serializers.ChoiceField(choices=["auto", "manual"])


class AssignInvigilatorSerializer(serializers.Serializer):
    autoAssign = serializers.BooleanField(required=False, default=False)
    examSlotId = serializers.UUIDField(required=False)
    facultyId = serializers.UUIDField(required=False)
