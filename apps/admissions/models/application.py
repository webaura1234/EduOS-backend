"""
Admissions — enquiry and application flow.

Covers the pre-enrollment pipeline:
  - Enquiry             → initial interest from a prospective student/parent
  - Application         → formal application submitted against an enquiry
  - ApplicationDocument → supporting documents uploaded with an application
  - Waitlist            → ranked hold list, promotable to application
"""

from django.db import models

from apps.admissions.enums import (
    ApplicationStatus,
    DocVerificationStatus,
    EnquirySource,
    EnquiryStatus,
)
from apps.core.models import BaseModel


class Enquiry(BaseModel):
    """Initial prospect interest (F-071)."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="enquiries"
    )
    source = models.CharField(max_length=15, choices=EnquirySource.choices)
    course = models.ForeignKey(
        "academics.Course", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="enquiries",
    )
    applicant_name = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    status = models.CharField(
        max_length=15, choices=EnquiryStatus.choices, default=EnquiryStatus.NEW, db_index=True
    )
    captured_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="captured_enquiries",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "admissions_enquiry"
        indexes = [models.Index(fields=["branch", "status", "created_at"])]

    def __str__(self):
        return f"Enquiry({self.applicant_name})"


class Application(BaseModel):
    """Formal application against an enquiry (F-072). Resumable wizard via `step`."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="applications"
    )
    enquiry = models.OneToOneField(
        Enquiry, on_delete=models.CASCADE, related_name="application"
    )
    course = models.ForeignKey(
        "academics.Course", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="applications",
    )
    # Resume state for the multi-step admission wizard (EC-FORM-02).
    step = models.JSONField(default=dict, blank=True)
    eligibility_result = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=15, choices=ApplicationStatus.choices,
        default=ApplicationStatus.DRAFT, db_index=True,
    )
    rejection_reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "admissions_application"
        indexes = [models.Index(fields=["branch", "status", "course"])]

    def __str__(self):
        return f"Application({self.enquiry.applicant_name}, {self.status})"


class ApplicationDocument(BaseModel):
    """Supporting document uploaded against an application (F-079)."""

    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="documents"
    )
    doc_type = models.CharField(max_length=50)
    s3_key = models.CharField(max_length=500, blank=True, default="")
    verification_status = models.CharField(
        max_length=15, choices=DocVerificationStatus.choices,
        default=DocVerificationStatus.PENDING,
    )
    verified_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="verified_documents",
    )

    class Meta:
        db_table = "admissions_application_document"

    def __str__(self):
        return f"Document({self.doc_type})"


class Waitlist(BaseModel):
    """Ranked waitlist entry, promotable to the application pipeline (F-084)."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="waitlist_entries"
    )
    application = models.OneToOneField(
        Application, on_delete=models.CASCADE, related_name="waitlist_entry"
    )
    course = models.ForeignKey(
        "academics.Course", on_delete=models.CASCADE, related_name="waitlist_entries"
    )
    rank = models.PositiveIntegerField()

    class Meta:
        db_table = "admissions_waitlist"
        unique_together = [("course", "rank")]
        indexes = [models.Index(fields=["course", "rank"])]

    def __str__(self):
        return f"Waitlist(#{self.rank})"
