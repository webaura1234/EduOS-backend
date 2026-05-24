"""
Custom authentication backends for the EduOS platform.

Provides a stub ``JWTAuthentication`` class referenced by
``REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]``.  The full JWT
verification logic (signature validation, token refresh, blacklisting)
will be added in a later sprint; this stub lets Django boot and returns
an ``AuthenticationFailed`` response for any request that carries a
Bearer token.
"""

import logging

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger("apps.core.authentication")


class JWTAuthentication(BaseAuthentication):
    """
    JSON Web Token authentication backend (stub).

    Behaviour
    ~~~~~~~~~
    * Reads the ``Authorization: Bearer <token>`` header.
    * If no ``Authorization`` header is present the request is treated as
      unauthenticated (returns ``None`` so DRF can try other backends or
      fall through to permission checks).
    * If a Bearer token **is** present, raises ``AuthenticationFailed``
      because the full verification pipeline is not yet implemented.

    Once the JWT verification layer is complete this class will decode
    the token, validate the signature against ``settings.JWT``, and
    return ``(user, validated_token)``.
    """

    AUTH_HEADER_TYPE = "Bearer"
    AUTH_HEADER_NAME = "HTTP_AUTHORIZATION"

    def authenticate(self, request):
        """
        Authenticate the request and return a ``(user, auth)`` tuple or
        ``None``.

        Returns
        -------
        tuple or None
            ``None`` when no credentials are supplied (anonymous request).

        Raises
        ------
        AuthenticationFailed
            When a Bearer token is present but cannot be validated (stub
            behaviour — always fails until the full JWT flow is built).
        """
        auth_header = request.META.get(self.AUTH_HEADER_NAME, "")

        if not auth_header:
            return None  # No credentials → anonymous request

        parts = auth_header.split()

        if parts[0] != self.AUTH_HEADER_TYPE:
            return None  # Not a Bearer token → let other backends try

        if len(parts) != 2:
            raise AuthenticationFailed(
                "Invalid Authorization header. Expected 'Bearer <token>'."
            )

        token = parts[1]

        # ── Stub: full verification not yet implemented ──
        logger.debug(
            "JWT token received but verification is not yet implemented."
        )
        raise AuthenticationFailed(
            "JWT authentication is not yet configured. "
            "Please complete the JWT verification setup."
        )

    def authenticate_header(self, request):
        """
        Return a string to be used as the ``WWW-Authenticate`` header in
        a ``401`` response.
        """
        return self.AUTH_HEADER_TYPE
