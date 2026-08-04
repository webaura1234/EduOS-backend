"""Execute a StudentImportJob row-by-row and write an error report."""

from __future__ import annotations

import csv
import io
import logging

from apps.admissions.imports.apply import apply_row
from apps.admissions.models.student_import import StudentImportJob, StudentImportStatus
from apps.admissions.queries import student_import as job_q
from apps.integrations.adapters.s3 import get_s3_adapter

logger = logging.getLogger(__name__)


def execute_import_job(*, job_id: str, celery_task_id: str = "") -> None:
    try:
        job = StudentImportJob.objects.select_related(
            "branch", "branch__tenant", "academic_year", "requested_by"
        ).get(pk=job_id, is_active=True)
    except StudentImportJob.DoesNotExist:
        logger.error("StudentImportJob %s not found", job_id)
        return

    if celery_task_id:
        job_q.update_job(job, {"celery_task_id": celery_task_id, "status": StudentImportStatus.RUNNING})
    else:
        job_q.update_job(job, {"status": StudentImportStatus.RUNNING})

    rows = job.row_payload or []
    success = failed = warning = processed = 0
    error_rows: list[dict] = []

    for item in rows:
        processed += 1
        severity = item.get("severity")
        if severity == "error":
            failed += 1
            error_rows.append(_error_line(item, "; ".join(item.get("errors") or ["Validation error"])))
            _bump(job, processed=processed, failed=failed, success=success, warning=warning)
            continue

        try:
            apply_row(
                action=item.get("action") or "create",
                branch=job.branch,
                academic_year=job.academic_year,
                data=item.get("data") or {},
                user=job.requested_by,
            )
            success += 1
            if severity == "warning":
                warning += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            msg = _exc_message(exc)
            error_rows.append(_error_line(item, msg))
            logger.exception("Student import row %s failed: %s", item.get("rowNumber"), msg)

        _bump(job, processed=processed, failed=failed, success=success, warning=warning)

    error_key = ""
    if error_rows:
        error_key = _upload_error_csv(job, error_rows)

    job_q.update_job(
        job,
        {
            "status": StudentImportStatus.COMPLETED,
            "success_count": success,
            "failed_count": failed,
            "warning_count": warning,
            "processed_count": processed,
            "error_report_key": error_key,
            "error": "" if not error_rows else f"{failed} row(s) failed",
        },
    )


def _bump(job, *, processed, failed, success, warning):
    # Periodic progress flush every 10 rows (and always on last via caller).
    if processed % 10 == 0:
        job_q.update_job(
            job,
            {
                "processed_count": processed,
                "failed_count": failed,
                "success_count": success,
                "warning_count": warning,
            },
        )


def _exc_message(exc) -> str:
    detail = getattr(exc, "detail", None)
    if detail is None:
        return str(exc) or exc.__class__.__name__
    if isinstance(detail, dict):
        parts = []
        for k, v in detail.items():
            if isinstance(v, (list, tuple)):
                parts.append(f"{k}: {', '.join(str(x) for x in v)}")
            else:
                parts.append(f"{k}: {v}")
        return "; ".join(parts) or str(detail)
    if isinstance(detail, list):
        return "; ".join(str(x) for x in detail)
    return str(detail)


def _error_line(item: dict, message: str) -> dict:
    data = item.get("data") or {}
    return {
        "rowNumber": item.get("rowNumber"),
        "admission_number": data.get("admission_number", ""),
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "error": message,
    }


def _upload_error_csv(job: StudentImportJob, error_rows: list[dict]) -> str:
    buf = io.StringIO()
    fields = ["rowNumber", "admission_number", "first_name", "last_name", "error"]
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(error_rows)
    content = buf.getvalue().encode("utf-8-sig")
    key = f"imports/{job.tenant_id}/{job.pk}/errors.csv"
    get_s3_adapter().upload(key=key, content=content, content_type="text/csv")
    return key
