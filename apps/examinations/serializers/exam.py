"""Serializers — grade scales, exams, and schedule slots (camelCase)."""

from rest_framework import serializers

from apps.examinations.enums import ExamType
from apps.examinations.helpers import split_datetime
from apps.examinations.models import ExamScheduleSlot


class GradeScaleSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    courseId = serializers.UUIDField(source="course_id", read_only=True)
    name = serializers.CharField(read_only=True)
    bands = serializers.JSONField(read_only=True)
    graceMarksMax = serializers.IntegerField(source="grace_marks_max", read_only=True)
    isDefault = serializers.BooleanField(source="is_default", read_only=True)
    version = serializers.IntegerField(read_only=True)


class CreateGradeScaleSerializer(serializers.Serializer):
    courseId = serializers.UUIDField()
    name = serializers.CharField(max_length=100)
    bands = serializers.JSONField()
    graceMarksMax = serializers.IntegerField(required=False, default=0, min_value=0)
    isDefault = serializers.BooleanField(required=False, default=False)


class UpdateGradeScaleSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    bands = serializers.JSONField(required=False)
    graceMarksMax = serializers.IntegerField(required=False, min_value=0)
    isDefault = serializers.BooleanField(required=False)
    version = serializers.IntegerField(required=False)


class ExamSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    examType = serializers.CharField(source="exam_type", read_only=True)
    academicPeriodId = serializers.UUIDField(source="academic_period_id", read_only=True)
    examFeePaise = serializers.IntegerField(source="exam_fee_paise", read_only=True)
    marksDeadline = serializers.DateTimeField(source="marks_deadline", read_only=True, allow_null=True)
    isPublished = serializers.BooleanField(source="is_published", read_only=True)
    resultStatus = serializers.CharField(source="result_status", read_only=True)
    version = serializers.IntegerField(read_only=True)


class CreateExamSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    examType = serializers.ChoiceField(choices=ExamType.values, default=ExamType.INTERNAL)
    academicPeriodId = serializers.UUIDField()
    examFeePaise = serializers.IntegerField(required=False, default=0, min_value=0)
    marksDeadline = serializers.DateTimeField(required=False, allow_null=True)


class UpdateExamSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    examType = serializers.ChoiceField(choices=ExamType.values, required=False)
    academicPeriodId = serializers.UUIDField(required=False)
    examFeePaise = serializers.IntegerField(required=False, min_value=0)
    marksDeadline = serializers.DateTimeField(required=False, allow_null=True)
    version = serializers.IntegerField(required=False)


class ExamScheduleSlotSerializer(serializers.Serializer):
    """Matches frontend ExamSlot shape."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.SerializerMethodField()
    classSectionId = serializers.UUIDField(source="batch_id", read_only=True)
    classLabel = serializers.CharField(source="batch.name", read_only=True)
    subjectId = serializers.UUIDField(source="subject_id", read_only=True)
    subjectName = serializers.CharField(source="subject.name", read_only=True)
    date = serializers.SerializerMethodField()
    startTime = serializers.SerializerMethodField()
    endTime = serializers.SerializerMethodField()
    roomId = serializers.UUIDField(source="room_id", read_only=True)
    roomName = serializers.CharField(source="room.name", read_only=True)
    status = serializers.SerializerMethodField()
    marksEntryDeadlineAt = serializers.SerializerMethodField()
    version = serializers.IntegerField(read_only=True)

    def get_name(self, obj: ExamScheduleSlot) -> str:
        return f"{obj.exam.name} — {obj.subject.name}"

    def get_date(self, obj: ExamScheduleSlot) -> str:
        return split_datetime(obj.start_at)[0]

    def get_startTime(self, obj: ExamScheduleSlot) -> str:
        return split_datetime(obj.start_at)[1]

    def get_endTime(self, obj: ExamScheduleSlot) -> str:
        from django.utils import timezone

        local = timezone.localtime(obj.end_at)
        return local.strftime("%H:%M")

    def get_status(self, obj: ExamScheduleSlot) -> str:
        return "published" if obj.exam.is_published else "draft"

    def get_marksEntryDeadlineAt(self, obj: ExamScheduleSlot):
        deadline = obj.exam.marks_deadline
        return deadline.isoformat() if deadline else None


class CreateScheduleSlotSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    classSectionId = serializers.UUIDField()
    subjectId = serializers.UUIDField()
    date = serializers.DateField()
    startTime = serializers.CharField()
    endTime = serializers.CharField()
    roomId = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["draft", "published"], required=False, default="draft")
    maxMarks = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
    override = serializers.BooleanField(required=False, default=False)


class UpdateScheduleSlotSerializer(serializers.Serializer):
    classSectionId = serializers.UUIDField(required=False)
    subjectId = serializers.UUIDField(required=False)
    date = serializers.DateField(required=False)
    startTime = serializers.CharField(required=False)
    endTime = serializers.CharField(required=False)
    roomId = serializers.UUIDField(required=False)
    maxMarks = serializers.DecimalField(max_digits=6, decimal_places=2, required=False)
    override = serializers.BooleanField(required=False, default=False)
    version = serializers.IntegerField(required=False)
