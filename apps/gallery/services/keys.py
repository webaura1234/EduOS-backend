"""R2 key building and path safety for gallery assets."""

from __future__ import annotations

import re
import uuid

from django.utils.text import slugify

from apps.academics.helpers import batch_display_label

_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9-_.]*$")
_UNSAFE = re.compile(r"[^a-z0-9-]+")


def branch_storage_code(branch) -> str:
    code = (getattr(branch, "code", "") or "").strip()
    if code:
        return _sanitize_segment(code.lower())
    return str(branch.pk).replace("-", "")[:8]


def batch_storage_slug(batch) -> str:
    label = batch_display_label(batch)
    slug = slugify(label).replace("-", "-") or str(batch.pk).replace("-", "")[:8]
    return _sanitize_segment(slug)


def _sanitize_segment(value: str) -> str:
    cleaned = _UNSAFE.sub("-", value.lower().strip())
    cleaned = cleaned.strip("-") or "item"
    if not _SEGMENT_RE.match(cleaned):
        raise ValueError(f"Invalid storage segment: {value!r}")
    return cleaned


def validate_key(key: str) -> None:
    if not key or ".." in key or key.startswith("/"):
        raise ValueError("Invalid object key")
    for part in key.split("/"):
        if part in ("", ".", ".."):
            raise ValueError("Path traversal detected in object key")


def generate_staging_key() -> str:
    return f"staging/{uuid.uuid4().hex}"


def generate_image_uuid() -> str:
    return uuid.uuid4().hex


def build_album_prefix(*, branch, batch, album_slug: str) -> str:
    branch_code = branch_storage_code(branch)
    album_part = _sanitize_segment(album_slug)
    if batch is None:
        return f"school/{branch_code}/gallery/school/{album_part}"
    batch_part = batch_storage_slug(batch)
    return f"school/{branch_code}/gallery/classes/{batch_part}/{album_part}"


def build_image_keys(*, branch, batch, album_slug: str, image_uuid: str | None = None) -> tuple[str, str]:
    prefix = build_album_prefix(branch=branch, batch=batch, album_slug=album_slug)
    uid = image_uuid or generate_image_uuid()
    main_key = f"{prefix}/{uid}.webp"
    thumb_key = f"{prefix}/thumbnail/{uid}.webp"
    validate_key(main_key)
    validate_key(thumb_key)
    return main_key, thumb_key
