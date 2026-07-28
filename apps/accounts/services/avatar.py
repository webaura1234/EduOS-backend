"""User avatar storage helpers (S3/R2 keys + signed URLs)."""

from apps.integrations.adapters.s3 import get_s3_adapter

ALLOWED_AVATAR_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_AVATAR_BYTES = 5 * 1024 * 1024


def avatar_object_key(*, tenant_id, user_id) -> str:
    """Object key for a user's avatar. Tenant users and platform owners use different prefixes."""
    if tenant_id:
        return f"tenants/{tenant_id}/users/{user_id}/avatar.webp"
    return f"platform/users/{user_id}/avatar.webp"


def avatar_url_for_key(key: str | None) -> str | None:
    if not key:
        return None
    return get_s3_adapter().signed_url(key=key)


def avatar_url_for_user(user) -> str | None:
    return avatar_url_for_key(getattr(user, "avatar_s3_key", None) or None)


def validate_avatar_upload(*, content_type: str, file_size: int) -> str | None:
    if file_size <= 0:
        return "File is empty."
    if file_size > MAX_AVATAR_BYTES:
        return f"File exceeds maximum size of {MAX_AVATAR_BYTES} bytes."
    if content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
        return f"Unsupported type: {content_type}"
    return None
