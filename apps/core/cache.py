"""Shared short-TTL memoisation for expensive read aggregates.

Roll-up endpoints that fan out across branches (dashboards, operations overview,
tenant settings) are memoised in the shared cache keyed by tenant/branch. The view
helper stamps ``lastUpdated`` + a real ``X-Cache-Age`` header so the UI can show
freshness. Safe and reversible: identical computation, just briefly memoised.

Cache backend is Redis in prod, LocMemCache in dev/test (see config.settings). TTL is
tunable per environment via ``DASHBOARD_CACHE_TTL_SECONDS`` (default 60s). A dashboard
being <=60s stale is acceptable and is reported honestly to the client.
"""

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.response import Response

DEFAULT_TTL = getattr(settings, "DASHBOARD_CACHE_TTL_SECONDS", 60)


def get_or_compute(cache_key: str, compute, ttl: int = DEFAULT_TTL):
    """Return ``(data, computed_at)``, memoising ``compute()`` for ``ttl`` seconds.

    ``computed_at`` is the timezone-aware moment the cached payload was produced, so
    callers can report the real cache age instead of a hardcoded zero.
    """
    hit = cache.get(cache_key)
    if hit is not None:
        data, computed_at = hit
        return data, computed_at
    data = compute()
    computed_at = timezone.now()
    cache.set(cache_key, (data, computed_at), ttl)
    return data, computed_at


def cached_response(data: dict, computed_at=None) -> Response:
    """Wrap ``data`` in a DRF Response, stamping freshness metadata.

    ``computed_at`` is when the payload was produced; for live (uncached) data pass
    ``None`` and ``X-Cache-Age`` is 0, otherwise it reflects the true age.
    """
    now = timezone.now()
    stamp = computed_at or now
    age = max(int((now - stamp).total_seconds()), 0)
    resp = Response({**data, "lastUpdated": stamp.isoformat()})
    resp["X-Cache-Age"] = str(age)
    return resp
