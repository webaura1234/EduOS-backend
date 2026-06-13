"""S3 storage adapter — sandbox-first, mirroring the payments gateway pattern.

`SandboxS3` records uploads deterministically and returns a stub signed URL (no network);
`LiveS3` is the production stub (boto3 wired at deploy). `get_s3_adapter()` reads
`settings.S3_MODE` (default "sandbox"). Tests assert against `SandboxS3.SINK`.
"""

from django.conf import settings


class SandboxS3:
    """In-memory S3: records uploads, returns a deterministic signed URL. No network."""

    SINK: dict = {}  # key -> bytes (test-inspectable)

    def upload(self, *, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        SandboxS3.SINK[key] = content
        return key

    def signed_url(self, *, key: str, ttl_seconds: int = 86400) -> str:
        return f"https://sandbox-s3.local/{key}?signature=stub&ttl={ttl_seconds}"

    def delete(self, *, key: str) -> None:
        SandboxS3.SINK.pop(key, None)


class LiveS3:
    """Production stub — real boto3 client wired at deploy."""

    def upload(self, *, key, content, content_type="application/octet-stream") -> str:  # pragma: no cover
        raise NotImplementedError("LiveS3 requires AWS credentials (deploy-time).")

    def signed_url(self, *, key, ttl_seconds=86400) -> str:  # pragma: no cover
        raise NotImplementedError("LiveS3 requires AWS credentials (deploy-time).")

    def delete(self, *, key) -> None:  # pragma: no cover
        raise NotImplementedError("LiveS3 requires AWS credentials (deploy-time).")


def get_s3_adapter():
    mode = getattr(settings, "S3_MODE", "sandbox")
    return LiveS3() if mode == "live" else SandboxS3()
