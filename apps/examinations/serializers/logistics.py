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


class SeatingPreflightItemSerializer(serializers.Serializer):
    examSlotId = serializers.CharField()
    classLabel = serializers.CharField()
    subjectName = serializers.CharField()
    registeredCount = serializers.IntegerField()
    roomCapacity = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["ready", "warning", "blocked"])
    issues = serializers.ListField(child=serializers.CharField())


class SeatingPreflightSerializer(serializers.Serializer):
    totalSlots = serializers.IntegerField()
    readyCount = serializers.IntegerField()
    items = SeatingPreflightItemSerializer(many=True)


class SeatingBulkErrorSerializer(serializers.Serializer):
    examSlotId = serializers.CharField()
    errors = serializers.DictField()


class GenerateSeatingSerializer(serializers.Serializer):
    examSlotId = serializers.UUIDField(required=False)
    examSlotIds = serializers.ListField(child=serializers.UUIDField(), required=False)
    roomIds = serializers.ListField(child=serializers.UUIDField(), required=False)
    mode = serializers.ChoiceField(choices=["per_slot", "combined"], required=False, default="per_slot")
    seatingOrder = serializers.ChoiceField(
        choices=["random", "alphabetical"], required=False, default="random"
    )
    seed = serializers.IntegerField(required=False, allow_null=True)


class PreflightSeatingSerializer(serializers.Serializer):
    examSlotIds = serializers.ListField(child=serializers.UUIDField(), required=False)


class CreateSeatingSessionSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    hallRoomId = serializers.UUIDField()
    examSlotIds = serializers.ListField(child=serializers.UUIDField(), min_length=1)


class SeatingSessionSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    hallRoomId = serializers.CharField()
    hallRoomName = serializers.CharField()
    startAt = serializers.CharField()
    endAt = serializers.CharField()
    examSlotIds = serializers.ListField(child=serializers.CharField())


class InvigilationAssignmentSerializer(serializers.Serializer):
    examSlotId = serializers.CharField()
    facultyId = serializers.CharField()
    facultyName = serializers.CharField()
    assignedAt = serializers.CharField()
    assignedBy = serializers.ChoiceField(choices=["auto", "manual"])


class AssignInvigilatorSerializer(serializers.Serializer):
    autoAssign = serializers.BooleanField(required=False, default=False)
    mode = serializers.ChoiceField(choices=["add", "replace", "remove"], required=False, default="add")
    examSlotId = serializers.UUIDField(required=False)
    facultyId = serializers.UUIDField(required=False)
    replaceFacultyId = serializers.UUIDField(required=False)
