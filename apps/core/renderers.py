"""
Custom response renderers for the EduOS platform.

Provides ``StandardJSONRenderer`` — wraps all API responses in a uniform
JSON envelope so frontend clients always receive a predictable shape.
"""

from rest_framework.renderers import JSONRenderer


class StandardJSONRenderer(JSONRenderer):
    """
    Render API responses inside a standard envelope::

        {
            "success": true,
            "data": { ... },
            "message": "OK"
        }

    Error responses (4xx / 5xx) are wrapped as::

        {
            "success": false,
            "data": null,
            "message": "Error description",
            "errors": { ... }      // optional field-level errors
        }

    The envelope is **not** applied to responses that are already
    wrapped (i.e. when ``renderer_context["response"]`` already contains
    a ``success`` key) or to non-dict data (e.g. raw file downloads
    handled by other renderers).
    """

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """
        Wrap *data* in the standard envelope before JSON serialisation.
        """
        renderer_context = renderer_context or {}
        response = renderer_context.get("response")
        status_code = response.status_code if response else 200

        # If the data is already wrapped or is not a dict, pass through.
        if isinstance(data, dict) and "success" in data:
            return super().render(data, accepted_media_type, renderer_context)

        is_success = 200 <= status_code < 400

        if is_success:
            envelope = {
                "success": True,
                "data": data,
                "message": "OK",
            }
        else:
            # DRF exception handler may return ``{"detail": "..."}`` or a
            # dict of field-level errors.
            message = "An error occurred."
            errors = None

            if isinstance(data, dict):
                # Single-message errors from DRF use the "detail" key.
                message = data.pop("detail", message)
                # Whatever remains are field-level validation errors.
                if data:
                    errors = data
            elif isinstance(data, list):
                message = "; ".join(str(item) for item in data)

            envelope = {
                "success": False,
                "data": None,
                "message": str(message),
            }
            if errors:
                envelope["errors"] = errors

        return super().render(envelope, accepted_media_type, renderer_context)
