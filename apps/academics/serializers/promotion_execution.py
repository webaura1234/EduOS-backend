"""Serializers — Promotion execution (Phase 3)."""

from rest_framework import serializers


class PromotionExecuteSerializer(serializers.Serializer):
    confirmationPhrase = serializers.CharField(min_length=3, max_length=100)
    confirmToken = serializers.CharField(min_length=32, max_length=128, required=False, allow_blank=True)
