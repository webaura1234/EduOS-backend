"""S3 storage adapter — sandbox-first, mirroring the payments gateway pattern.

`SandboxS3` records uploads deterministically and returns a stub signed URL (no network);
`LiveS3` is the production stub (boto3 wired at deploy). `get_s3_adapter()` reads
`settings.S3_MODE` (default "sandbox"). Tests assert against `SandboxS3.SINK`.
"""

from django.conf import settings


class S3NotFoundError(Exception):
    """Raised by download() when the key doesn't exist."""


class SandboxS3:
    """In-memory S3: records uploads, returns a deterministic signed URL. No network."""

    SINK: dict = {}  # key -> bytes (test-inspectable)

    def upload(self, *, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        SandboxS3.SINK[key] = content
        return key

    def download(self, *, key: str) -> bytes:
        if key not in SandboxS3.SINK:
            raise S3NotFoundError(key)
        return SandboxS3.SINK[key]

    def signed_url(self, *, key: str, ttl_seconds: int = 86400) -> str:
        return f"https://sandbox-s3.local/{key}?signature=stub&ttl={ttl_seconds}"

    def delete(self, *, key: str) -> None:
        SandboxS3.SINK.pop(key, None)


class LiveS3:
    """Production S3 client backed by boto3."""

    def __init__(self):  # pragma: no cover
        import boto3
        from django.conf import settings as _s
        self._client = boto3.client(
            "s3",
            region_name=getattr(_s, "AWS_S3_REGION_NAME", "ap-south-1"),
            aws_access_key_id=getattr(_s, "AWS_ACCESS_KEY_ID", ""),
            aws_secret_access_key=getattr(_s, "AWS_SECRET_ACCESS_KEY", ""),
        )
        self._bucket = getattr(_s, "AWS_STORAGE_BUCKET_NAME", "eduos-uploads")

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
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )

    def delete(self, *, key: str) -> None:  # pragma: no cover
        self._client.delete_object(Bucket=self._bucket, Key=key)


def get_s3_adapter():
    mode = getattr(settings, "S3_MODE", "sandbox")
    return LiveS3() if mode == "live" else SandboxS3()
