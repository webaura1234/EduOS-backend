"""Serializers — results compute, publish, revise, grace, analytics (camelCase)."""

from rest_framework import serializers


class PublishResultsSerializer(serializers.Serializer):
    confirmToken = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class ReviseResultsSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class GraceMarksEntrySerializer(serializers.Serializer):
    studentId = serializers.UUIDField()
    subjectId = serializers.UUIDField()
    graceMarks = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)


class GraceMarksSerializer(serializers.Serializer):
    entries = GraceMarksEntrySerializer(many=True)


class StudentResultSerializer(serializers.Serializer):
    studentId = serializers.UUIDField()
    studentName = serializers.CharField()
    classLabel = serializers.CharField()
    examId = serializers.CharField()
    publicationId = serializers.UUIDField(allow_null=True)
    totalMarks = serializers.FloatField()
    percentage = serializers.FloatField()
    grade = serializers.CharField()
    gpa = serializers.FloatField(allow_null=True)
    isPass = serializers.BooleanField()
    arrearSubjects = serializers.ListField(child=serializers.DictField())


class ResultPublishConfirmationSerializer(serializers.Serializer):
    confirmToken = serializers.CharField()
    createdAt = serializers.CharField()
    expiresAt = serializers.CharField()
    summary = serializers.DictField()
    studentResults = StudentResultSerializer(many=True)


class ResultPublicationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    examId = serializers.CharField()
    publishedAt = serializers.CharField()
    publishedByUserId = serializers.CharField()
    revisionNo = serializers.IntegerField()
    note = serializers.CharField()
    snapshotHash = serializers.CharField()


class AnalyticsTopperSerializer(serializers.Serializer):
    studentId = serializers.CharField()
    studentName = serializers.CharField()
    percent = serializers.FloatField()


class AnalyticsBreakdownSerializer(serializers.Serializer):
    band = serializers.CharField()
    count = serializers.IntegerField()


class ResultsAnalyticsSerializer(serializers.Serializer):
    examId = serializers.CharField()
    generatedAt = serializers.CharField()
    passPercent = serializers.IntegerField()
    absentCount = serializers.IntegerField()
    averagePercent = serializers.FloatField()
    toppers = AnalyticsTopperSerializer(many=True)
    breakdown = AnalyticsBreakdownSerializer(many=True)


class ResultsSlotPreflightSerializer(serializers.Serializer):
    examSlotId = serializers.CharField()
    classLabel = serializers.CharField()
    subjectName = serializers.CharField()
    registeredCount = serializers.IntegerField()
    enteredCount = serializers.IntegerField()
    submittedCount = serializers.IntegerField()
    status = serializers.CharField()


class ResultsPreflightSerializer(serializers.Serializer):
    examId = serializers.CharField()
    examName = serializers.CharField()
    isPublished = serializers.BooleanField()
    resultStatus = serializers.CharField()
    slots = ResultsSlotPreflightSerializer(many=True)
    readyCount = serializers.IntegerField()
    totalSlots = serializers.IntegerField()
    canPublish = serializers.BooleanField()
    blockers = serializers.ListField(child=serializers.CharField())


class ResultPublicationSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    examId = serializers.CharField()
    publishedAt = serializers.CharField()
    publishedByUserId = serializers.CharField()
    revisionNo = serializers.IntegerField()
    note = serializers.CharField()
    isCurrent = serializers.BooleanField()


class ResultsStatusSerializer(serializers.Serializer):
    examId = serializers.CharField()
    isPublished = serializers.BooleanField()
    resultStatus = serializers.CharField()
    publications = ResultPublicationSummarySerializer(many=True)


class ReportCardSerializer(serializers.Serializer):
    canDownload = serializers.BooleanField()
    blockedReason = serializers.CharField(required=False, allow_blank=True)
    fileName = serializers.CharField()
    content = serializers.CharField()
