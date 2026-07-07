"""Image validation, compression, WebP conversion, and thumbnail generation."""

from __future__ import annotations

import hashlib
import io

from django.conf import settings
from PIL import Image, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

ALLOWED_MIME = frozenset({"image/jpeg", "image/png", "image/webp"})
ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


def _max_bytes() -> int:
    return getattr(settings, "GALLERY_MAX_UPLOAD_BYTES", 10 * 1024 * 1024)


def _max_dimension() -> int:
    return getattr(settings, "GALLERY_MAX_DIMENSION_PX", 4096)


def _thumb_max() -> int:
    return getattr(settings, "GALLERY_THUMBNAIL_MAX_PX", 400)


def _webp_quality() -> int:
    return getattr(settings, "GALLERY_WEBP_QUALITY", 82)


def validate_upload_meta(*, file_name: str, content_type: str, file_size: int) -> None:
    if file_size <= 0:
        raise ValidationError({"fileSize": "File is empty."})
    if file_size > _max_bytes():
        raise ValidationError({"fileSize": f"File exceeds maximum size of {_max_bytes()} bytes."})
    if content_type not in ALLOWED_MIME:
        raise ValidationError({"contentType": f"Unsupported type: {content_type}"})
    ext = "." + file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise ValidationError({"fileName": f"Unsupported extension: {ext}"})


def process_image(content: bytes) -> tuple[bytes, bytes, int, int, str]:
    """Return (main_webp, thumb_webp, width, height, sha256_hex)."""
    if len(content) > _max_bytes():
        raise ValidationError({"fileSize": "File exceeds maximum upload size."})

    try:
        img = Image.open(io.BytesIO(content))
        img.load()
    except UnidentifiedImageError as exc:
        raise ValidationError({"file": "Invalid or corrupted image file."}) from exc

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    elif img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background

    max_dim = _max_dimension()
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    width, height = img.size
    content_hash = hashlib.sha256(content).hexdigest()

    main_buf = io.BytesIO()
    img.save(main_buf, format="WEBP", quality=_webp_quality(), method=4)
    main_bytes = main_buf.getvalue()

    thumb = img.copy()
    thumb.thumbnail((_thumb_max(), _thumb_max()), Image.Resampling.LANCZOS)
    thumb_buf = io.BytesIO()
    thumb.save(thumb_buf, format="WEBP", quality=_webp_quality(), method=4)
    thumb_bytes = thumb_buf.getvalue()

    return main_bytes, thumb_bytes, width, height, content_hash
