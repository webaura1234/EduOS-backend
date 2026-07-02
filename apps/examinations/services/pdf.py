"""PDF generation for examination artifacts (hall ticket, report card, transcript).

Generated via weasyprint (HTML → PDF) for proper branding/table support. Storage goes
through the S3 adapter; reads try S3 first and fall back to MEDIA_ROOT for PDFs written
before this migration (no backfill — old files simply stay on local disk).
"""

from __future__ import annotations

import base64
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string

from apps.core.exports.pdf import render_pdf
from apps.integrations.adapters.s3 import S3NotFoundError, get_s3_adapter


def generate_hall_ticket_pdf(
    *,
    institution_name: str,
    exam_name: str,
    student_name: str,
    roll_number: str,
    regulation: str = "",
) -> bytes:
    """Render the hall ticket HTML template to PDF bytes."""
    html = render_to_string("pdf/hall_ticket.html", {
        "institution_name": institution_name,
        "exam_name": exam_name,
        "student_name": student_name,
        "roll_number": roll_number,
        "regulation": regulation,
    })
    return render_pdf(html)


def hall_ticket_file_key(*, branch_id, registration_id) -> str:
    return f"hall_tickets/{branch_id}/{registration_id}.pdf"


def store_hall_ticket_pdf(*, branch_id, registration_id, pdf_bytes: bytes) -> str:
    """Upload PDF bytes to S3 and return the storage key."""
    key = hall_ticket_file_key(branch_id=branch_id, registration_id=registration_id)
    get_s3_adapter().upload(key=key, content=pdf_bytes, content_type="application/pdf")
    return key


def hall_ticket_content_payload(pdf_bytes: bytes) -> str:
    """Frontend-compatible content field (base64 PDF)."""
    return base64.b64encode(pdf_bytes).decode("ascii")


def generate_result_pdf(
    *,
    title: str,
    institution_name: str,
    exam_name: str,
    student_name: str,
    class_label: str = "",
    grade: str,
    percentage: str,
    gpa: str = "",
    subjects: list[dict] | None = None,
) -> bytes:
    """Render the report card / marksheet HTML template to PDF bytes."""
    html = render_to_string("pdf/report_card.html", {
        "title": title,
        "institution_name": institution_name,
        "exam_name": exam_name,
        "student_name": student_name,
        "class_label": class_label,
        "grade": grade,
        "percentage": percentage,
        "gpa": gpa,
        "subjects": subjects or [],
    })
    return render_pdf(html)


def report_card_file_key(*, branch_id, exam_id, student_id) -> str:
    return f"report_cards/{branch_id}/{exam_id}/{student_id}.pdf"


def marksheet_file_key(*, branch_id, exam_id, student_id) -> str:
    return f"marksheets/{branch_id}/{exam_id}/{student_id}.pdf"


def store_result_pdf(*, key: str, pdf_bytes: bytes) -> str:
    get_s3_adapter().upload(key=key, content=pdf_bytes, content_type="application/pdf")
    return key


def _read_media_root(key: str) -> bytes | None:
    """Legacy fallback — PDFs generated before the S3 migration live here."""
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
    path = media_root / key
    if not path.is_file():
        return None
    return path.read_bytes()


def read_result_pdf(key: str) -> bytes | None:
    """Load a stored report card or marksheet PDF. Tries S3 first, then MEDIA_ROOT."""
    if not key:
        return None
    try:
        return get_s3_adapter().download(key=key)
    except S3NotFoundError:
        return _read_media_root(key)


def read_hall_ticket_pdf(key: str) -> bytes | None:
    """Load a stored hall ticket PDF. Tries S3 first, then MEDIA_ROOT."""
    return read_result_pdf(key)
