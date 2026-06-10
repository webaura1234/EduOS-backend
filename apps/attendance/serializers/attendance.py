"""Serializers — sessions, records, marking (camelCase I/O)."""

from rest_framework import serializers

from apps.attendance.enums import AttendanceStatus, SessionStatus


class AttendanceSessionSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    batchSubjectId = serializers.UUIDField(source="batch_subject_id", read_only=True)
    date = serializers.DateField(read_only=True)
    periodSlotId = serializers.UUIDField(source="period_slot_id", read_only=True)
    facultyId = serializers.UUIDField(source="faculty_id", read_only=True, allow_null=True)
    status = serializers.CharField(read_only=True)
    isExamDay = serializers.BooleanField(source="is_exam_day", read_only=True)
    version = serializers.IntegerField(read_only=True)


class AttendanceRecordSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    sessionId = serializers.UUIDField(source="session_id", read_only=True)
    studentId = serializers.UUIDField(source="student_id", read_only=True)
    status = serializers.CharField(read_only=True)
    lateMark = serializers.BooleanField(source="late_mark", read_only=True)
    markedAt = serializers.DateTimeField(source="marked_at", read_only=True)
    version = serializers.IntegerField(read_only=True)


class OpenSessionSerializer(serializers.Serializer):
    date = serializers.DateField()
    # Session mode:
    batchSubjectId = serializers.UUIDField(required=False, allow_null=True)
    periodSlotId = serializers.UUIDField(required=False, allow_null=True)
    # Day mode:
    batchId = serializers.UUIDField(required=False, allow_null=True)
    facultyId = serializers.UUIDField(required=False, allow_null=True)
    isExamDay = serializers.BooleanField(required=False, default=False)


class _MarkItemSerializer(serializers.Serializer):
    studentId = serializers.UUIDField()
    status = serializers.ChoiceField(choices=AttendanceStatus.values, required=False,
                                     default=AttendanceStatus.PRESENT)
    geoLat = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    geoLng = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    geoValid = serializers.BooleanField(required=False, default=True)


class MarkSessionSerializer(serializers.Serializer):
    marks = _MarkItemSerializer(many=True)


class UpdateSessionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=SessionStatus.values)
    version = serializers.IntegerField(required=False)


class CorrectRecordSerializer(serializers.Serializer):
    newStatus = serializers.ChoiceField(choices=AttendanceStatus.values)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    version = serializers.IntegerField(required=False)
