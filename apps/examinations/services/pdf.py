"""PDF generation for examination artifacts (hall ticket, report card, transcript)."""

from __future__ import annotations

import base64
from pathlib import Path

from django.conf import settings


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def generate_hall_ticket_pdf(
    *,
    institution_name: str,
    exam_name: str,
    student_name: str,
    roll_number: str,
    regulation: str = "",
) -> bytes:
    """Build a minimal single-page PDF with hall ticket details."""
    lines = [
        "Hall Ticket",
        f"Institution: {institution_name}",
        f"Exam: {exam_name}",
        f"Student: {student_name}",
        f"Roll No: {roll_number}",
    ]
    if regulation:
        lines.append(f"Regulation: {regulation}")

    y = 750
    stream_parts = []
    for line in lines:
        stream_parts.append(f"BT /F1 12 Tf 50 {y} Td ({_escape_pdf_text(line)}) Tj ET")
        y -= 18
    stream = "\n".join(stream_parts)

    objects = []
    objects.append("1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")
    objects.append("2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj")
    objects.append(
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj"
    )
    objects.append(f"4 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj")
    objects.append("5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj")

    pdf = "%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj + "\n"
    xref_start = len(pdf)
    pdf += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n"
    pdf += f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF"
    return pdf.encode("latin-1")


def hall_ticket_file_key(*, branch_id, registration_id) -> str:
    return f"hall_tickets/{branch_id}/{registration_id}.pdf"


def store_hall_ticket_pdf(*, branch_id, registration_id, pdf_bytes: bytes) -> str:
    """Persist PDF bytes locally and return the storage key (F-301 seam)."""
    key = hall_ticket_file_key(branch_id=branch_id, registration_id=registration_id)
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
    path = media_root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_bytes)
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
    grade: str,
    percentage: str,
    gpa: str = "",
) -> bytes:
    """Minimal single-page PDF for school report card or college marksheet."""
    lines = [
        title,
        f"Institution: {institution_name}",
        f"Exam: {exam_name}",
        f"Student: {student_name}",
        f"Grade: {grade}",
        f"Percentage: {percentage}%",
    ]
    if gpa:
        lines.append(f"SGPA: {gpa}")

    y = 750
    stream_parts = []
    for line in lines:
        stream_parts.append(f"BT /F1 12 Tf 50 {y} Td ({_escape_pdf_text(line)}) Tj ET")
        y -= 18
    stream = "\n".join(stream_parts)

    objects = []
    objects.append("1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")
    objects.append("2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj")
    objects.append(
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj"
    )
    objects.append(f"4 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj")
    objects.append("5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj")

    pdf = "%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj + "\n"
    xref_start = len(pdf)
    pdf += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n"
    pdf += f"trailer << /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF"
    return pdf.encode("latin-1")


def report_card_file_key(*, branch_id, exam_id, student_id) -> str:
    return f"report_cards/{branch_id}/{exam_id}/{student_id}.pdf"


def marksheet_file_key(*, branch_id, exam_id, student_id) -> str:
    return f"marksheets/{branch_id}/{exam_id}/{student_id}.pdf"


def store_result_pdf(*, key: str, pdf_bytes: bytes) -> str:
    media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
    path = media_root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf_bytes)
    return key
