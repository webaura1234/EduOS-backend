"""Serializers — student/parent hub responses (camelCase)."""

from rest_framework import serializers


class HubStudentSerializer(serializers.Serializer):
    studentId = serializers.CharField()
    name = serializers.CharField()
    classLabel = serializers.CharField()
    examFeePaid = serializers.BooleanField()


class HubExamSlotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    classSectionId = serializers.CharField()
    classLabel = serializers.CharField()
    subjectId = serializers.CharField()
    subjectName = serializers.CharField()
    date = serializers.CharField()
    startTime = serializers.CharField()
    endTime = serializers.CharField()
    roomId = serializers.CharField()
    status = serializers.CharField()


class HubPublishedResultSerializer(serializers.Serializer):
    examSlotId = serializers.CharField()
    examLabel = serializers.CharField(default="")
    subjectName = serializers.CharField()
    publishedAt = serializers.CharField()
    percent = serializers.FloatField(allow_null=True)
    remark = serializers.CharField()


class StudentExamHubSerializer(serializers.Serializer):
    institutionType = serializers.CharField()
    student = HubStudentSerializer()
    upcomingExams = HubExamSlotSerializer(many=True)
    hallTicketAvailable = serializers.BooleanField()
    publishedResults = HubPublishedResultSerializer(many=True)


class GpaSummarySerializer(serializers.Serializer):
    sgpa = serializers.FloatField()
    cgpa = serializers.FloatField()
    calculatedAt = serializers.CharField()


class StudentResultsHubSerializer(serializers.Serializer):
    institutionType = serializers.CharField()
    results = HubPublishedResultSerializer(many=True)
    gpa = GpaSummarySerializer(allow_null=True)
