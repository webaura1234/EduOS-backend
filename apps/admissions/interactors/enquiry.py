"""Interactors — enquiry capture + conversion to application (F-071/F-072)."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.admissions.enums import ApplicationStatus, EnquiryStatus
from apps.admissions.queries import application as app_q
from apps.admissions.queries import enquiry as enquiry_q


@transaction.atomic
def capture_enquiry(*, branch, source, applicant_name, course=None, date_of_birth=None,
                    phone="", email="", captured_by=None, notes=""):
    if not applicant_name or not applicant_name.strip():
        raise ValidationError({"applicantName": "Applicant name is required."})
    return enquiry_q.create_enquiry(
        branch=branch, source=source, applicant_name=applicant_name.strip(), course=course,
        date_of_birth=date_of_birth, phone=phone, email=email, captured_by=captured_by,
        notes=notes, user=captured_by,
    )


@transaction.atomic
def convert_enquiry_to_application(*, enquiry, course=None, user=None):
    if hasattr(enquiry, "application"):
        raise ValidationError({"enquiry": "This enquiry already has an application."})
    application = app_q.create_application(
        branch=enquiry.branch, enquiry=enquiry, course=course or enquiry.course,
        status=ApplicationStatus.SUBMITTED, step={"step": 1}, user=user,
    )
    enquiry_q.update_enquiry(enquiry, {"status": EnquiryStatus.CONVERTED}, user=user)
    return application
