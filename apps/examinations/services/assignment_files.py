"""Local file storage for assignment submissions (F-301 seam)."""

from pathlib import Path

from django.conf import settings


def submission_file_key(*, branch_id, assignment_id, student_id, file_name: str) -> str:
    safe_name = file_name.replace("/", "_").replace("\\", "_") or "submission.bin"
    return f"assignments/{branch_id}/{assignment_id}/{student_id}/{safe_name}"


def store_submission_file(*, key: str, content_bytes: bytes) -> str:
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
    path = media_root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content_bytes)
    return key


def attachment_name_from_key(file_key: str) -> str:
    if not file_key:
        return ""
    return file_key.rsplit("/", 1)[-1]
