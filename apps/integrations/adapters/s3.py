"""S3 / R2 storage adapter — sandbox-first, mirroring the payments gateway pattern.

`SandboxS3` records uploads deterministically and returns stub signed URLs (no network);
`LiveS3` is the production client (boto3, R2-compatible via endpoint_url).
`get_s3_adapter()` reads `settings.S3_MODE` (default "sandbox").
Tests assert against `SandboxS3.SINK`.
"""

from django.conf import settings


class S3NotFoundError(Exception):
    """Raised by download() when the key doesn't exist."""


class SandboxS3:
    """In-memory object storage for tests and local dev."""

    SINK: dict = {}  # key -> bytes (test-inspectable)

    @property
    def bucket(self) -> str:
        return getattr(settings, "R2_BUCKET_NAME", None) or getattr(
            settings, "AWS_STORAGE_BUCKET_NAME", "eduos-uploads",
        )

    def upload(self, *, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        SandboxS3.SINK[key] = content
        return key

    def download(self, *, key: str) -> bytes:
        if key not in SandboxS3.SINK:
            raise S3NotFoundError(key)
        return SandboxS3.SINK[key]

    def signed_url(self, *, key: str, ttl_seconds: int = 86400) -> str:
        # Sandbox bytes are not on CDN — callers should prefer GalleryStorageService
        # which builds a local media proxy URL. Keep a deterministic stub for tests.
        return f"https://sandbox-s3.local/{key}?signature=stub&ttl={ttl_seconds}"

    def presigned_upload_url(
        self,
        *,
        key: str,
        content_type: str = "application/octet-stream",
        ttl_seconds: int = 3600,
    ) -> str:
        return f"https://sandbox-s3.local/{key}?upload=stub&ttl={ttl_seconds}&type={content_type}"

    def delete(self, *, key: str) -> None:
        SandboxS3.SINK.pop(key, None)

    def list_prefix(self, *, prefix: str) -> list[str]:
        return [k for k in SandboxS3.SINK if k.startswith(prefix)]

    def copy(self, *, source_key: str, dest_key: str) -> None:
        if source_key not in SandboxS3.SINK:
            raise S3NotFoundError(source_key)
        SandboxS3.SINK[dest_key] = SandboxS3.SINK[source_key]

    def move(self, *, source_key: str, dest_key: str) -> None:
        self.copy(source_key=source_key, dest_key=dest_key)
        self.delete(key=source_key)

    def delete_prefix(self, *, prefix: str) -> int:
        keys = self.list_prefix(prefix=prefix)
        for key in keys:
            self.delete(key=key)
        return len(keys)


class LiveS3:
    """Production object storage client backed by boto3 (AWS S3 or Cloudflare R2)."""

    def __init__(self):  # pragma: no cover
        import boto3
        from django.conf import settings as _s

        endpoint = getattr(_s, "R2_ENDPOINT_URL", "") or None
        # R2 only accepts: auto | wnam | enam | weur | eeur | apac | oc
        # — never AWS regions like ap-south-1.
        if endpoint:
            region = getattr(_s, "R2_REGION_NAME", "") or "auto"
        else:
            region = getattr(_s, "AWS_S3_REGION_NAME", "ap-south-1") or "ap-south-1"
        access_key = getattr(_s, "R2_ACCESS_KEY_ID", "") or getattr(_s, "AWS_ACCESS_KEY_ID", "")
        secret_key = getattr(_s, "R2_SECRET_ACCESS_KEY", "") or getattr(_s, "AWS_SECRET_ACCESS_KEY", "")

        client_kwargs = {
            "service_name": "s3",
            "region_name": region,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
        }
        if endpoint:
            client_kwargs["endpoint_url"] = endpoint

        self._client = boto3.client(**client_kwargs)
        self._bucket = (
            getattr(_s, "R2_BUCKET_NAME", "")
            or getattr(_s, "AWS_STORAGE_BUCKET_NAME", "eduos-uploads")
        )

    @property
    def bucket(self) -> str:  # pragma: no cover
        return self._bucket

    def upload(self, *, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:  # pragma: no cover
        self._client.put_object(Bucket=self._bucket, Key=key, Body=content, ContentType=content_type)
        return key

    def download(self, *, key: str) -> bytes:  # pragma: no cover
        from botocore.exceptions import ClientError
        try:
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
            return obj["Body"].read()
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404"):
                raise S3NotFoundError(key) from exc
            raise

    def signed_url(self, *, key: str, ttl_seconds: int = 86400) -> str:  # pragma: no cover
        public_base = getattr(settings, "R2_PUBLIC_BASE_URL", "")
        if public_base:
            from apps.gallery.services.storage import _public_cdn_usable
            if _public_cdn_usable(public_base):
                return f"{public_base.rstrip('/')}/{key}"
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )

    def presigned_upload_url(
        self,
        *,
        key: str,
        content_type: str = "application/octet-stream",
        ttl_seconds: int = 3600,
    ) -> str:  # pragma: no cover
        return self._client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=ttl_seconds,
        )

    def delete(self, *, key: str) -> None:  # pragma: no cover
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def list_prefix(self, *, prefix: str) -> list[str]:  # pragma: no cover
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                keys.append(item["Key"])
        return keys

    def copy(self, *, source_key: str, dest_key: str) -> None:  # pragma: no cover
        self._client.copy_object(
            Bucket=self._bucket,
            Key=dest_key,
            CopySource={"Bucket": self._bucket, "Key": source_key},
        )

    def move(self, *, source_key: str, dest_key: str) -> None:  # pragma: no cover
        self.copy(source_key=source_key, dest_key=dest_key)
        self.delete(key=source_key)

    def delete_prefix(self, *, prefix: str) -> int:  # pragma: no cover
        keys = self.list_prefix(prefix=prefix)
        if not keys:
            return 0
        for i in range(0, len(keys), 1000):
            batch = keys[i : i + 1000]
            self._client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
            )
        return len(keys)


def get_s3_adapter():
    mode = getattr(settings, "S3_MODE", "sandbox")
    return LiveS3() if mode == "live" else SandboxS3()
