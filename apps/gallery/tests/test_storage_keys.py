"""Storage key builder tests."""

from types import SimpleNamespace

import pytest

from apps.gallery.services.keys import build_album_prefix, generate_staging_key, validate_key


def test_staging_key_is_safe():
    key = generate_staging_key()
    validate_key(key)
    assert key.startswith("staging/")


def test_school_album_prefix():
    branch = SimpleNamespace(pk="abc", code="MC")
    prefix = build_album_prefix(branch=branch, batch=None, album_slug="annual-day")
    assert prefix == "school/mc/gallery/school/annual-day"


def test_path_traversal_rejected():
    with pytest.raises(ValueError):
        validate_key("../etc/passwd")
