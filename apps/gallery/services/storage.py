"""Gallery object storage — business layer over the S3/R2 adapter."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings

from apps.gallery.services import keys as key_builder
from apps.integrations.adapters.s3 import get_s3_adapter


def _hostname_is_loopback(hostname: str) -> bool:
    if not hostname:
        return False
    host = hostname.strip().lower().rstrip(".")
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = info[4][0]
        try:
            if ipaddress.ip_address(ip).is_loopback:
                return True
        except ValueError:
            continue
    return False


def _public_cdn_usable(public_base: str) -> bool:
    """False when CDN host resolves to loopback (common local /etc/hosts override)."""
    if not public_base:
        return False
    host = urlparse(public_base if "://" in public_base else f"https://{public_base}").hostname
    return not _hostname_is_loopback(host or "")


class GalleryStorageService:
    """All gallery R2 operations go through this service."""

    def __init__(self):
        self._adapter = get_s3_adapter()

    def generate_staging_key(self) -> str:
        return key_builder.generate_staging_key()

    def build_album_prefix(self, *, branch, batch, album_slug: str) -> str:
        return key_builder.build_album_prefix(branch=branch, batch=batch, album_slug=album_slug)

    def build_image_keys(self, *, branch, batch, album_slug: str, image_uuid: str | None = None) -> tuple[str, str]:
        return key_builder.build_image_keys(
            branch=branch, batch=batch, album_slug=album_slug, image_uuid=image_uuid,
        )

    def upload_file(self, *, key: str, content: bytes, content_type: str = "image/webp") -> str:
        key_builder.validate_key(key)
        return self._adapter.upload(key=key, content=content, content_type=content_type)

    def download_file(self, *, key: str) -> bytes:
        key_builder.validate_key(key)
        return self._adapter.download(key=key)

    def delete_file(self, *, key: str) -> None:
        if not key:
            return
        key_builder.validate_key(key)
        self._adapter.delete(key=key)

    def delete_folder(self, *, prefix: str) -> int:
        key_builder.validate_key(prefix.rstrip("/") + "/x")
        return self._adapter.delete_prefix(prefix=prefix)

    def copy_file(self, *, source_key: str, dest_key: str) -> None:
        key_builder.validate_key(source_key)
        key_builder.validate_key(dest_key)
        self._adapter.copy(source_key=source_key, dest_key=dest_key)

    def move_file(self, *, source_key: str, dest_key: str) -> None:
        key_builder.validate_key(source_key)
        key_builder.validate_key(dest_key)
        self._adapter.move(source_key=source_key, dest_key=dest_key)

    def list_files(self, *, prefix: str) -> list[str]:
        return self._adapter.list_prefix(prefix=prefix)

    def presigned_upload_url(
        self,
        *,
        key: str,
        content_type: str,
        ttl_seconds: int = 3600,
    ) -> str:
        key_builder.validate_key(key)
        return self._adapter.presigned_upload_url(
            key=key, content_type=content_type, ttl_seconds=ttl_seconds,
        )

    def _is_live_storage(self) -> bool:
        return getattr(settings, "S3_MODE", "sandbox") == "live"

    def generate_public_url(self, key: str) -> str | None:
        if not key:
            return None
        # Never invent CDN URLs for in-memory sandbox objects.
        if not self._is_live_storage():
            return None
        public_base = getattr(settings, "R2_PUBLIC_BASE_URL", "")
        if not _public_cdn_usable(public_base):
            return None
        return f"{public_base.rstrip('/')}/{key}"

    def generate_signed_url(self, key: str, *, ttl_seconds: int | None = None) -> str | None:
        if not key:
            return None
        # Public CDN URLs only when live storage is actually usable.
        from apps.integrations.adapters.s3 import _live_config_usable

        mode = getattr(settings, "S3_MODE", "sandbox")
        if mode == "live" and _live_config_usable():
            public = self.generate_public_url(key)
            if public:
                return public
        ttl = ttl_seconds or getattr(settings, "AWS_S3_PRESIGNED_URL_EXPIRY", 86400)
        if not self._is_live_storage():
            from apps.gallery.services.media_urls import build_sandbox_media_url
            return build_sandbox_media_url(key, ttl_seconds=ttl)
        return self._adapter.signed_url(key=key, ttl_seconds=ttl)

    def resolve_image_urls(self, image) -> tuple[str | None, str | None]:
        if image.external_url:
            return image.external_url, image.external_url
        main = self.generate_signed_url(image.image_key) if image.image_key else None
        thumb = self.generate_signed_url(image.thumbnail_key) if image.thumbnail_key else main
        return main, thumb

    def resolve_cover_url(self, album) -> str | None:
        if not album.cover_image_key:
            return None
        return self.generate_signed_url(album.cover_image_key)


def get_gallery_storage() -> GalleryStorageService:
    return GalleryStorageService()
