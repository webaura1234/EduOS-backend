"""
Configurable enquiry form (F-071+) — one form per branch, Google-Forms style.

`EnquiryForm.fields` is an ordered list of admin-defined custom fields layered on
top of the always-present core fields (applicant name + phone). The same schema
drives the admin capture form and the public shareable form, and is validated on
submission so custom answers land in `Enquiry.custom_fields`.
"""

from django.db import models

from apps.core.models import BaseModel


class EnquiryFieldType(models.TextChoices):
    TEXT = "text", "Short text"
    TEXTAREA = "textarea", "Paragraph"
    EMAIL = "email", "Email"
    PHONE = "phone", "Phone"
    NUMBER = "number", "Number"
    DATE = "date", "Date"
    SELECT = "select", "Dropdown"
    CHECKBOX = "checkbox", "Checkbox"


# Field types whose answers are free-form strings validated only for presence/format.
FIELD_TYPES_WITH_OPTIONS = {EnquiryFieldType.SELECT}


class EnquiryForm(BaseModel):
    """The single configurable enquiry form for a branch."""

    branch = models.OneToOneField(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="enquiry_form",
    )
    title = models.CharField(max_length=150, default="Admission Enquiry")
    description = models.TextField(
        blank=True,
        default="Fill in your details and our team will get back to you.",
    )
    # Ordered list of custom field definitions. Each item:
    #   {key, label, type, required: bool, options: [str], placeholder: str}
    fields = models.JSONField(default=list, blank=True)
    # When False the public link is disabled (form only usable by staff).
    is_public = models.BooleanField(default=True)

    class Meta:
        db_table = "admissions_enquiry_form"
        verbose_name = "Enquiry Form"
        verbose_name_plural = "Enquiry Forms"

    def __str__(self):
        return f"EnquiryForm({self.branch_id}, {len(self.fields or [])} custom fields)"
