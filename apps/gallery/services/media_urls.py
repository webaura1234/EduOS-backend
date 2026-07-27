"""HMAC-signed sandbox media URLs for local gallery viewing without R2 CDN."""

from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

from django.conf import settings


def _secret() -> bytes:
    return str(settings.SECRET_KEY).encode()


def sign_media_key(key: str, *, ttl_seconds: int = 86400) -> tuple[str, str]:
    """Return (exp, sig) for a storage key."""
    exp = str(int(time.time()) + ttl_seconds)
    msg = f"{key}:{exp}".encode()
    sig = hmac.new(_secret(), msg, hashlib.sha256).hexdigest()
    return exp, sig


def verify_media_sig(*, key: str, exp: str, sig: str) -> bool:
    if not key or not exp or not sig:
        return False
    try:
        if int(exp) < int(time.time()):
            return False
    except (TypeError, ValueError):
        return False
    expected = hmac.new(_secret(), f"{key}:{exp}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def build_sandbox_media_url(key: str, *, ttl_seconds: int = 86400) -> str:
    """Absolute Django URL that streams sandbox (or live) object bytes after signature check."""
    exp, sig = sign_media_key(key, ttl_seconds=ttl_seconds)
    base = getattr(settings, "GALLERY_SANDBOX_MEDIA_BASE", "http://127.0.0.1:8000").rstrip("/")
    qs = urlencode({"key": key, "exp": exp, "sig": sig})
    return f"{base}/api/v1/gallery/media/?{qs}"
