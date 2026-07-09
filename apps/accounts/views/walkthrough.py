from __future__ import annotations

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import WalkthroughCompletion
from apps.accounts.serializers.walkthrough import (
    WalkthroughCompleteManySerializer,
    WalkthroughCompleteSerializer,
)


class MeWalkthroughsView(APIView):
    """
    GET  /api/v1/auth/me/walkthroughs/
      → { completed: string[] }

    POST /api/v1/auth/me/walkthroughs/  { key }
      → { completed: string[] }

    POST /api/v1/auth/me/walkthroughs/  { keys: string[] }
      → { completed: string[] }

    "Skip" and "Finish" are both modeled as completion: once a key is recorded,
    the walkthrough never auto-appears again unless the user explicitly replays.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        keys = list(
            WalkthroughCompletion.objects.filter(user=request.user)
            .order_by("key")
            .values_list("key", flat=True)
        )
        return Response({"completed": keys}, status=status.HTTP_200_OK)

    def post(self, request) -> Response:
        one = WalkthroughCompleteSerializer(data=request.data)
        many = WalkthroughCompleteManySerializer(data=request.data)
        if one.is_valid():
            keys = [one.validated_data["key"]]
        elif many.is_valid():
            keys = many.validated_data["keys"]
        else:
            # Return the more helpful validation errors.
            return Response(
                {"errors": {"key": one.errors.get("key"), "keys": many.errors.get("keys")}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Insert idempotently (unique per user+key).
        created_any = False
        for key in keys:
            try:
                with transaction.atomic():
                    WalkthroughCompletion.objects.create(user=request.user, key=key)
                    created_any = True
            except IntegrityError:
                continue

        # Always return the full set (frontend uses as a cache seed).
        completed = list(
            WalkthroughCompletion.objects.filter(user=request.user)
            .order_by("key")
            .values_list("key", flat=True)
        )
        return Response(
            {"completed": completed, "created": created_any},
            status=status.HTTP_200_OK,
        )

