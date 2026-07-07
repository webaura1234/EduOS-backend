"""Image pipeline tests."""

from io import BytesIO

import pytest
from PIL import Image
from rest_framework.exceptions import ValidationError

from apps.gallery.services.image_pipeline import process_image, validate_upload_meta


def _jpeg_bytes() -> bytes:
    img = Image.new("RGB", (800, 600), color=(10, 120, 200))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_validate_upload_meta_rejects_large():
    with pytest.raises(ValidationError):
        validate_upload_meta(file_name="x.jpg", content_type="image/jpeg", file_size=50_000_000)


def test_process_image_returns_webp():
    raw = _jpeg_bytes()
    main, thumb, width, height, digest = process_image(raw)
    assert width == 800 and height == 600
    assert len(digest) == 64
    assert main[:4] == b"RIFF"  # WebP container
    assert len(thumb) < len(main)
