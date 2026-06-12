"""Queries — exam registration and hall tickets (all ORM here)."""

from apps.examinations.models import ExamRegistration, HallTicket


def list_registrations(exam_id, *, batch_id=None):
    qs = (
        ExamRegistration.objects.filter(exam_id=exam_id, is_active=True)
        .select_related("student", "student__student_profile__user", "student__batch", "fee_invoice")
        .order_by("student__student_profile__user__first_name", "student__student_profile__user__last_name")
    )
    if batch_id:
        qs = qs.filter(student__batch_id=batch_id)
    return qs


def get_registration(branch_id, registration_id) -> ExamRegistration | None:
    try:
        return ExamRegistration.objects.select_related(
            "exam",
            "exam__branch",
            "exam__branch__tenant",
            "exam__academic_period",
            "student",
            "student__student_profile__user",
            "student__batch",
            "student__batch__course",
            "fee_invoice",
            "hall_ticket",
        ).get(
            exam__branch_id=branch_id,
            pk=registration_id,
            is_active=True,
        )
    except (ExamRegistration.DoesNotExist, ValueError, TypeError):
        return None


def registration_exists(exam_id, student_id) -> bool:
    return ExamRegistration.objects.filter(
        exam_id=exam_id, student_id=student_id, is_active=True
    ).exists()


def create_registration(
    *,
    exam_id,
    student_id,
    fee_invoice_id=None,
    fee_paid=False,
    is_arrear=False,
    user=None,
) -> ExamRegistration:
    return ExamRegistration.objects.create(
        exam_id=exam_id,
        student_id=student_id,
        fee_invoice_id=fee_invoice_id,
        fee_paid=fee_paid,
        is_arrear=is_arrear,
        created_by=user,
        updated_by=user,
    )


def update_registration(registration: ExamRegistration, fields: dict, user=None) -> ExamRegistration:
    for k, v in fields.items():
        setattr(registration, k, v)
    if fields:
        registration.version += 1
        if user:
            registration.updated_by = user
        registration.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return registration


def get_hall_ticket(registration_id) -> HallTicket | None:
    try:
        return HallTicket.objects.select_related("registration").get(
            registration_id=registration_id, is_active=True
        )
    except (HallTicket.DoesNotExist, ValueError, TypeError):
        return None


def create_hall_ticket(
    *,
    registration_id,
    file_key,
    roll_number,
    regulation="",
    generated_at,
    user=None,
) -> HallTicket:
    return HallTicket.objects.create(
        registration_id=registration_id,
        file_key=file_key,
        roll_number=roll_number,
        regulation=regulation,
        generated_at=generated_at,
        created_by=user,
        updated_by=user,
    )


def update_hall_ticket(ticket: HallTicket, fields: dict, user=None) -> HallTicket:
    for k, v in fields.items():
        setattr(ticket, k, v)
    if fields:
        ticket.version += 1
        if user:
            ticket.updated_by = user
        ticket.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return ticket
