"""Interactors — application step-save, documents, and rejection (F-072/F-079/F-083)."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.admissions.enums import ApplicationStatus, DocVerificationStatus
from apps.admissions.queries import application as app_q


@transaction.atomic
def save_application_step(*, branch_id, application_id, step, user=None):
    application = app_q.get_application(branch_id, application_id)
    if not application:
        raise ValidationError({"application": "Application not found."})
    if application.status == ApplicationStatus.ENROLLED:
        raise ValidationError({"application": "Cannot update an enrolled application."})
    return app_q.update_application(application, {"step": step}, user=user)


@transaction.atomic
def add_application_document(*, branch_id, application_id, doc_type, s3_key="", user=None):
    application = app_q.get_application(branch_id, application_id)
    if not application:
        raise ValidationError({"application": "Application not found."})
    if application.status == ApplicationStatus.ENROLLED:
        raise ValidationError({"application": "Cannot add documents to an enrolled application."})
    if not doc_type or not doc_type.strip():
        raise ValidationError({"docType": "Document type is required."})
    return app_q.add_document(application=application, doc_type=doc_type.strip(), s3_key=s3_key, user=user)


@transaction.atomic
def verify_document(*, branch_id, document_id, verification_status, user=None):
    document = app_q.get_document(branch_id, document_id)
    if not document:
        raise ValidationError({"document": "Document not found."})
    if verification_status not in DocVerificationStatus.values:
        raise ValidationError({"verificationStatus": f"Invalid status: {verification_status}"})
    
    fields = {
        "verification_status": verification_status,
        "verified_by": user,
    }
    return app_q.update_document(document, fields, user=user)


@transaction.atomic
def reject_application(*, branch_id, application_id, rejection_reason, user=None):
    application = app_q.get_application(branch_id, application_id)
    if not application:
        raise ValidationError({"application": "Application not found."})
    if application.status == ApplicationStatus.ENROLLED:
        raise ValidationError({"application": "Cannot reject an enrolled application."})
    if not rejection_reason or not rejection_reason.strip():
        raise ValidationError({"rejectionReason": "Rejection reason is required."})
    
    fields = {
        "status": ApplicationStatus.REJECTED,
        "rejection_reason": rejection_reason.strip(),
    }
    return app_q.update_application(application, fields, user=user)
