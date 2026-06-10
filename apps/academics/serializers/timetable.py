"""Serializers — PeriodSlot, Room, Timetable, TimetableEntry."""

from rest_framework import serializers

from apps.academics.models import DayOfWeek, TimetableEntryStatus


class PeriodSlotSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    sequence = serializers.IntegerField(read_only=True)
    startTime = serializers.TimeField(source="start_time", read_only=True)
    endTime = serializers.TimeField(source="end_time", read_only=True)
    version = serializers.IntegerField(read_only=True)


class CreatePeriodSlotSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    sequence = serializers.IntegerField(min_value=1)
    startTime = serializers.TimeField()
    endTime = serializers.TimeField()


class UpdatePeriodSlotSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50, required=False)
    sequence = serializers.IntegerField(min_value=1, required=False)
    startTime = serializers.TimeField(required=False)
    endTime = serializers.TimeField(required=False)
    version = serializers.IntegerField(required=False)


class RoomSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    capacity = serializers.IntegerField(read_only=True)
    isLab = serializers.BooleanField(source="is_lab", read_only=True)
    version = serializers.IntegerField(read_only=True)


class CreateRoomSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    code = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    capacity = serializers.IntegerField(required=False, default=40, min_value=1)
    isLab = serializers.BooleanField(required=False, default=False)


class UpdateRoomSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    capacity = serializers.IntegerField(required=False, min_value=1)
    isLab = serializers.BooleanField(required=False)
    version = serializers.IntegerField(required=False)


class TimetableSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    batchId = serializers.UUIDField(source="batch_id", read_only=True)
    academicPeriodId = serializers.UUIDField(source="academic_period_id", read_only=True)
    name = serializers.CharField(read_only=True)
    isPublished = serializers.BooleanField(source="is_published", read_only=True)
    version = serializers.IntegerField(read_only=True)


class CreateTimetableSerializer(serializers.Serializer):
    batchId = serializers.UUIDField()
    academicPeriodId = serializers.UUIDField()


class TimetableEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    timetableId = serializers.UUIDField(source="timetable_id", read_only=True)
    batchSubjectId = serializers.UUIDField(source="batch_subject_id", read_only=True)
    periodSlotId = serializers.UUIDField(source="period_slot_id", read_only=True)
    dayOfWeek = serializers.IntegerField(source="day_of_week", read_only=True)
    facultyId = serializers.UUIDField(source="faculty_id", read_only=True, allow_null=True)
    roomId = serializers.UUIDField(source="room_id", read_only=True, allow_null=True)
    status = serializers.CharField(read_only=True)
    version = serializers.IntegerField(read_only=True)


class CreateTimetableEntrySerializer(serializers.Serializer):
    batchSubjectId = serializers.UUIDField()
    periodSlotId = serializers.UUIDField()
    dayOfWeek = serializers.ChoiceField(choices=DayOfWeek.values)
    facultyId = serializers.UUIDField(required=False, allow_null=True)
    roomId = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=TimetableEntryStatus.values, required=False, default=TimetableEntryStatus.ACTIVE
    )


class UpdateTimetableEntrySerializer(serializers.Serializer):
    batchSubjectId = serializers.UUIDField(required=False)
    periodSlotId = serializers.UUIDField(required=False)
    dayOfWeek = serializers.ChoiceField(choices=DayOfWeek.values, required=False)
    facultyId = serializers.UUIDField(required=False, allow_null=True)
    roomId = serializers.UUIDField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=TimetableEntryStatus.values, required=False)
    version = serializers.IntegerField(required=False)


class TimetableActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["publish"])
    timetableId = serializers.UUIDField()
    version = serializers.IntegerField(required=False)
