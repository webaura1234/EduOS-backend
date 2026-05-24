"""
Custom Django middleware for the EduOS platform.

Provides:
- ``TenantMiddleware`` — multi-tenant isolation via JWT / header inspection.
- ``CorrelationIdMiddleware`` — request tracing with ``X-Correlation-ID``.
- ``RequestLoggingMiddleware`` — structured access-log for every request.
"""

import logging
import time
import uuid

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger("apps.core.middleware")

# ──────────────────────────────────────────────────────────────
# Tenant Middleware
# ──────────────────────────────────────────────────────────────


class TenantMiddleware(MiddlewareMixin):
    """
    Extract the tenant identifier from the incoming request and attach it
    as ``request.tenant_id`` so downstream code can scope queries.

    Resolution order
    ~~~~~~~~~~~~~~~~
    1. ``X-Tenant-ID`` request header (useful for service-to-service calls).
    2. ``tenant_id`` claim inside a JWT ``Authorization: Bearer <token>``
       header (decoded without verification at this layer — actual JWT
       validation is handled by the authentication backend).
    3. Falls back to ``None`` when neither source is available (e.g.
       unauthenticated or public endpoints).
    """

    # HTTP header Django normalises to META key
    TENANT_HEADER = "HTTP_X_TENANT_ID"

    def process_request(self, request):
        """Attach ``tenant_id`` to the request object."""
        tenant_id = self._resolve_tenant(request)
        request.tenant_id = tenant_id
        return None  # continue processing

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_tenant(self, request) -> str | None:
        """Return tenant_id from header or JWT payload, or ``None``."""
        # 1. Explicit header
        tenant_id = request.META.get(self.TENANT_HEADER)
        if tenant_id:
            return tenant_id

        # 2. Try to read from JWT payload (best-effort, no verification)
        tenant_id = self._tenant_from_jwt(request)
        if tenant_id:
            return tenant_id

        return None

    @staticmethod
    def _tenant_from_jwt(request) -> str | None:
        """
        Attempt to decode the JWT payload and extract ``tenant_id``.

        Uses *no* signature verification — this middleware only needs
        the claim value; authentication is enforced elsewhere.
        """
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ", 1)[1]
        try:
            import base64
            import json

            # JWT structure: header.payload.signature
            parts = token.split(".")
            if len(parts) != 3:
                return None

            # Decode the payload (second segment) — add padding.
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding

            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            return payload.get("tenant_id")
        except Exception:
            return None


# ──────────────────────────────────────────────────────────────
# Correlation-ID Middleware
# ──────────────────────────────────────────────────────────────


class CorrelationIdMiddleware(MiddlewareMixin):
    """
    Ensure every request/response carries a unique ``X-Correlation-ID``.

    If the incoming request already includes the header (e.g. from an API
    gateway or upstream service), the existing value is reused; otherwise a
    new UUID-4 is generated.  The ID is attached to ``request.correlation_id``
    and echoed back on the response.
    """

    HEADER_NAME = "X-Correlation-ID"
    META_KEY = "HTTP_X_CORRELATION_ID"

    def process_request(self, request):
        """Read or create the correlation ID."""
        correlation_id = request.META.get(self.META_KEY, str(uuid.uuid4()))
        request.correlation_id = correlation_id
        return None

    def process_response(self, request, response):
        """Echo the correlation ID on the outgoing response."""
        correlation_id = getattr(request, "correlation_id", str(uuid.uuid4()))
        response[self.HEADER_NAME] = correlation_id
        return response


# ──────────────────────────────────────────────────────────────
# Request Logging Middleware
# ──────────────────────────────────────────────────────────────


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Log every HTTP request with method, path, status code, and duration.

    Emits an ``INFO``-level log line once the response has been produced,
    including the tenant and correlation IDs when available.
    """

    def process_request(self, request):
        """Record the request start time."""
        request._request_start_time = time.monotonic()
        return None

    def process_response(self, request, response):
        """Log request summary after the response is ready."""
        duration_ms = 0.0
        start = getattr(request, "_request_start_time", None)
        if start is not None:
            duration_ms = (time.monotonic() - start) * 1000.0

        logger.info(
            "%s %s %s %.2fms",
            request.method,
            request.get_full_path(),
            response.status_code,
            duration_ms,
            extra={
                "http_method": request.method,
                "http_path": request.get_full_path(),
                "http_status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "tenant_id": getattr(request, "tenant_id", None),
                "correlation_id": getattr(request, "correlation_id", None),
            },
        )
        return response
