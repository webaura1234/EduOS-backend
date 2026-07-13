"""Serializers — Academic year promotion workspace."""

from rest_framework import serializers

from apps.academics.models.promotion import PromotionAction


class TargetYearCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=20)
    startDate = serializers.DateField()
    endDate = serializers.DateField()

    def validate(self, attrs):
        if attrs["endDate"] <= attrs["startDate"]:
            raise serializers.ValidationError({"endDate": "End date must be after start date."})
        return attrs


class PromotionStartSerializer(serializers.Serializer):
    branchId = serializers.UUIDField(required=False)
    sourceYearId = serializers.UUIDField()
    targetYearId = serializers.UUIDField(required=False)
    targetYearCreate = TargetYearCreateSerializer(required=False)

    def validate(self, attrs):
        if not attrs.get("targetYearId") and not attrs.get("targetYearCreate"):
            raise serializers.ValidationError(
                {"targetYearId": "Provide targetYearId or targetYearCreate."}
            )
        return attrs


class PromotionOverrideSerializer(serializers.Serializer):
    finalAction = serializers.ChoiceField(choices=[a.value for a in PromotionAction])
    reason = serializers.CharField(min_length=10, max_length=2000)


class PromotionBulkOverrideSerializer(serializers.Serializer):
    finalAction = serializers.ChoiceField(choices=[a.value for a in PromotionAction])
    reason = serializers.CharField(min_length=10, max_length=2000)
    decisionIds = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=False,
        max_length=5000,
    )
    filterAction = serializers.ChoiceField(
        choices=[a.value for a in PromotionAction],
        required=False,
    )
    courseId = serializers.UUIDField(required=False)
    batchId = serializers.UUIDField(required=False)

    def validate(self, attrs):
        has_ids = bool(attrs.get("decisionIds"))
        has_filter = bool(
            attrs.get("filterAction") or attrs.get("courseId") or attrs.get("batchId")
        )
        if not has_ids and not has_filter:
            raise serializers.ValidationError(
                {"decisionIds": "Provide decisionIds or a filter (filterAction/courseId/batchId)."}
            )
        return attrs


class PromotionReopenReviewSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=10, max_length=2000)


class PromotionDecisionsQuerySerializer(serializers.Serializer):
    branchId = serializers.UUIDField(required=False)
    courseId = serializers.UUIDField(required=False)
    batchId = serializers.UUIDField(required=False)
    action = serializers.ChoiceField(
        choices=[a.value for a in PromotionAction],
        required=False,
    )
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    pageSize = serializers.IntegerField(required=False, default=50, min_value=1, max_value=2000)
