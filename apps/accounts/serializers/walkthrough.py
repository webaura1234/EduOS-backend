from __future__ import annotations

from rest_framework import serializers


class WalkthroughCompleteSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=120, allow_blank=False, trim_whitespace=True)


class WalkthroughCompleteManySerializer(serializers.Serializer):
    keys = serializers.ListField(
        child=serializers.CharField(max_length=120, allow_blank=False, trim_whitespace=True),
        allow_empty=False,
    )

