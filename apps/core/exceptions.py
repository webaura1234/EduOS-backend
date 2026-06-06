"""
Custom exception handling for the EduOS platform.

Provides ``custom_exception_handler`` — the project-wide handler
referenced by ``REST_FRAMEWORK["EXCEPTION_HANDLER"]``.  It extends
DRF's default handler to ensure every error response conforms to the
standard JSON envelope used by ``StandardJSONRenderer``.
"""

import logging

from django.http import Http404
from django.core.exceptions import PermissionDenied
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("apps.core.exceptions")


class GoneError(APIException):
    """HTTP 410 — the requested resource is no longer available (e.g. a used/expired token)."""

    status_code = status.HTTP_410_GONE
    default_detail = "This resource is no longer available."
    default_code = "gone"


class ServiceUnavailableError(APIException):
    """HTTP 503 — a downstream dependency (e.g. the SMS gateway) is temporarily unavailable."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Service temporarily unavailable. Please try again in a few minutes."
    default_code = "service_unavailable"


def custom_exception_handler(exc, context):
    """
    Handle exceptions raised during DRF view processing.

    Behaviour
    ~~~~~~~~~
    1. Delegates to DRF's built-in handler first (handles
       ``APIException`` subclasses and Django's ``Http404`` /
       ``PermissionDenied``).
    2. If DRF returned a response, normalises its payload into the
       standard ``{success, data, message}`` envelope.
    3. If DRF returned ``None`` (unhandled exception), logs the error
       and returns a generic ``500`` response so the client still
       receives a well-formed envelope.

    Parameters
    ----------
    exc : Exception
        The exception that was raised.
    context : dict
        Context provided by DRF, including ``"view"``, ``"request"``,
        and ``"args"`` / ``"kwargs"``.

    Returns
    -------
    rest_framework.response.Response
    """
    # Let DRF handle known exception types.
    response = drf_exception_handler(exc, context)

    if response is not None:
        # Normalise into the standard envelope.
        errors = None
        if isinstance(response.data, dict):
            detail = response.data.get("detail")
            if detail:
                message = str(detail)
            else:
                message = "Validation error."
                errors = response.data
        elif isinstance(response.data, list):
            message = "; ".join(str(item) for item in response.data)
        else:
            message = str(response.data)

        envelope = {
            "success": False,
            "data": None,
            "message": message,
        }
        if errors:
            envelope["errors"] = errors

        response.data = envelope
        return response

    # ── Unhandled exception — log and return 500 ──
    logger.exception(
        "Unhandled exception in %s",
        context.get("view", "<unknown view>"),
        exc_info=exc,
    )

    return Response(
        {
            "success": False,
            "data": None,
            "message": "An unexpected error occurred. Please try again later.",
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
