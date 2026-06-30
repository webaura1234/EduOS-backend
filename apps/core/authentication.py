"""
Custom authentication backends for the EduOS platform.

JWTAuthentication — full implementation using PyJWT.

Reads the Authorization: Bearer <token> header, verifies the
access token signature and expiry, fetches the User from DB,
and returns (user, payload) for DRF to attach to request.user.
"""

import logging

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.queries.user import get_user_for_token
from apps.accounts.tokens import decode_access_token, is_access_token_revoked

logger = logging.getLogger("apps.core.authentication")


class JWTAuthentication(BaseAuthentication):
    """
    JSON Web Token authentication backend.

    Flow:
      1. Extract Bearer token from Authorization header.
      2. Decode and verify the access token (signature + expiry).
      3. Look up the User by sub claim (UUID).
      4. Verify user.is_active = True.
      5. Return (user, payload) — DRF attaches user to request.user.

    Returns None (anonymous) if no Authorization header is present,
    allowing public endpoints to pass through.
    """

    AUTH_HEADER_TYPE = "Bearer"
    AUTH_HEADER_NAME = "HTTP_AUTHORIZATION"

    def authenticate(self, request):
        """
        Authenticate the request.

        Returns (user, payload) on success, None if no token present.
        Raises AuthenticationFailed for invalid/expired tokens.
        """
        auth_header = request.META.get(self.AUTH_HEADER_NAME, "")

        if not auth_header:
            return None  # No credentials → anonymous request

        parts = auth_header.split()

        if parts[0] != self.AUTH_HEADER_TYPE:
            return None  # Not a Bearer token → let other backends try

        if len(parts) != 2:
            raise AuthenticationFailed(
                "Invalid Authorization header format. Expected: 'Bearer <token>'."
            )

        token = parts[1]

        # Decode and verify the access token
        payload = decode_access_token(token)

        # Check JTI blocklist (logout / password-change revocation via Redis)
        jti = payload.get("jti")
        if jti and is_access_token_revoked(jti):
            raise AuthenticationFailed("Token has been revoked. Please log in again.")

        # Fetch user from DB (DB access lives in the queries layer)
        user_id = payload.get("sub")
        user = get_user_for_token(user_id)
        if user is None:
            raise AuthenticationFailed("User not found.")

        # EC-AUTH-10: deactivated user → reject on the next call.
        if not user.is_active:
            raise AuthenticationFailed("User account is inactive.")

        # EC-AUTH-04: if the user's role changed since the token was issued,
        # the stale token must not keep working — force re-login.
        token_role = payload.get("role")
        if token_role is not None and token_role != user.role:
            raise AuthenticationFailed("Session is no longer valid. Please log in again.")

        logger.debug(
            "JWT auth: user=%s role=%s tenant=%s",
            user_id,
            user.role,
            user.tenant_id,
        )

        return (user, payload)

    def authenticate_header(self, request):
        """Return WWW-Authenticate header value for 401 responses."""
        return self.AUTH_HEADER_TYPE
