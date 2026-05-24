"""
Custom throttle classes for the EduOS platform.

Provides ``TenantRateThrottle`` — a per-tenant rate limiter referenced
by ``REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]``.
"""

from rest_framework.throttling import SimpleRateThrottle


class TenantRateThrottle(SimpleRateThrottle):
    """
    Rate-limit API requests on a per-tenant basis.

    Uses ``request.tenant_id`` (set by
    :class:`apps.core.middleware.TenantMiddleware`) as the cache key so
    each tenant organisation gets its own independent rate-limit bucket.

    The rate is configured via ``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["tenant"]``
    in Django settings (currently ``"100/minute"``).

    When ``request.tenant_id`` is not available (e.g. anonymous or
    public endpoints), the throttle falls back to the client's IP address
    so that unauthenticated traffic is still rate-limited.
    """

    scope = "tenant"

    def get_cache_key(self, request, view):
        """
        Return a unique cache key for the current tenant.

        Returns
        -------
        str
            ``"throttle_{scope}_{tenant_id}"`` when a tenant is
            identified, or ``"throttle_{scope}_{ip}"`` as a fallback.
        """
        tenant_id = getattr(request, "tenant_id", None)

        if tenant_id:
            return self.cache_format % {
                "scope": self.scope,
                "ident": tenant_id,
            }

        # Fallback: throttle by IP for anonymous / public requests.
        ident = self.get_ident(request)
        return self.cache_format % {
            "scope": self.scope,
            "ident": ident,
        }
