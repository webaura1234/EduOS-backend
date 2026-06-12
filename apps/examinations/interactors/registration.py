"""Interactors — exam registration and hall tickets."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.academics.helpers import is_college
from apps.examinations.exceptions import ExamFeeUnpaidError
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import registration as reg_q
from apps.examinations.services.pdf import (
    generate_hall_ticket_pdf,
    hall_ticket_content_payload,
    store_hall_ticket_pdf,
)
from apps.fees.enums import FeeComponentKind, InvoiceStatus
from apps.fees.queries.invoice import create_invoice, create_invoice_line, get_invoice_by_id
from apps.fees.queries.structure import billing_guardian_for_student, get_student_in_branch, students_in_batch


def _invoice_is_paid(invoice_id) -> bool:
    if not invoice_id:
        return True
    invoice = get_invoice_by_id(invoice_id)
    return invoice is not None and invoice.status == InvoiceStatus.PAID


def _create_exam_fee_invoice(*, branch, student, exam, user):
    due_date = exam.academic_period.end_date
    total_paise = exam.exam_fee_paise
    status = InvoiceStatus.PAID if total_paise == 0 else InvoiceStatus.DUE
    invoice = create_invoice(
        branch=branch,
        student=student,
        assignment=None,
        billing_guardian=billing_guardian_for_student(student),
        due_date=due_date,
        total_paise=total_paise,
        status=status,
        user=user,
    )
    if total_paise > 0:
        create_invoice_line(
            invoice=invoice,
            kind=FeeComponentKind.EXAM,
            label=f"Exam fee — {exam.name}",
            amount_paise=total_paise,
            user=user,
        )
    return invoice


@transaction.atomic
def bulk_register_exam(exam, *, branch, batch_id, is_arrear=False, tenant=None, user=None):
    if is_arrear and tenant and not is_college(tenant):
        raise ValidationError({"isArrear": "Arrear registration is college-only."})

    batch_students = list(students_in_batch(batch_id))
    if not batch_students:
        raise ValidationError({"classSectionId": "No active students found in this batch."})

    created = []
    skipped = []
    # `students_in_batch` returns active StudentEnrollment rows (enrollment seam).
    for student in batch_students:
        if reg_q.registration_exists(exam.pk, student.pk):
            skipped.append(str(student.student_profile_id))
            continue

        invoice = None
        fee_paid = exam.exam_fee_paise == 0
        if exam.exam_fee_paise >= 0:
            invoice = _create_exam_fee_invoice(branch=branch, student=student, exam=exam, user=user)
            fee_paid = invoice.status == InvoiceStatus.PAID

        registration = reg_q.create_registration(
            exam_id=exam.pk,
            student_id=student.pk,
            fee_invoice_id=invoice.pk if invoice else None,
            fee_paid=fee_paid,
            is_arrear=is_arrear,
            user=user,
        )
        created.append(registration)

    return {"registrations": created, "skippedStudentIds": skipped}


@transaction.atomic
def generate_hall_ticket(registration, *, branch, tenant=None, user=None):
    """Generate or return an existing hall ticket (EC-EXAM-01 fee gate)."""
    invoice_id = registration.fee_invoice_id
    if not _invoice_is_paid(invoice_id):
        raise ExamFeeUnpaidError()

    if registration.fee_paid is False:
        reg_q.update_registration(registration, {"fee_paid": True}, user=user)

    existing = reg_q.get_hall_ticket(registration.pk)
    if existing and existing.file_key:
        pdf_path = existing.file_key
        from pathlib import Path
        from django.conf import settings

        full_path = Path(getattr(settings, "MEDIA_ROOT", "media")) / pdf_path
        pdf_bytes = full_path.read_bytes() if full_path.exists() else b""
        return existing, pdf_bytes

    student = registration.student
    user_obj = student.user
    roll_number = user_obj.custom_login_id or str(student.pk)[:8]
    regulation = ""
    if tenant and is_college(tenant):
        course = getattr(student.current_batch, "course", None)
        regulation = getattr(course, "regulation", "") if course else ""

    institution_name = registration.exam.branch.tenant.name
    pdf_bytes = generate_hall_ticket_pdf(
        institution_name=institution_name,
        exam_name=registration.exam.name,
        student_name=user_obj.full_name,
        roll_number=roll_number,
        regulation=regulation,
    )
    file_key = store_hall_ticket_pdf(
        branch_id=branch.pk,
        registration_id=registration.pk,
        pdf_bytes=pdf_bytes,
    )
    now = timezone.now()
    if existing:
        ticket = reg_q.update_hall_ticket(
            existing,
            {"file_key": file_key, "roll_number": roll_number, "regulation": regulation, "generated_at": now},
            user=user,
        )
    else:
        ticket = reg_q.create_hall_ticket(
            registration_id=registration.pk,
            file_key=file_key,
            roll_number=roll_number,
            regulation=regulation,
            generated_at=now,
            user=user,
        )
    return ticket, pdf_bytes


def hall_ticket_result(registration, ticket, pdf_bytes: bytes) -> dict:
    student = registration.student
    return {
        "studentId": str(student.student_profile_id),
        "studentName": student.user.full_name,
        "canDownload": True,
        "content": hall_ticket_content_payload(pdf_bytes),
        "fileKey": ticket.file_key,
        "rollNumber": ticket.roll_number,
        "generatedAt": ticket.generated_at.isoformat() if ticket.generated_at else "",
    }
