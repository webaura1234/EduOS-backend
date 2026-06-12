"""Admissions query layer — all ORM lives in these modules."""

from apps.admissions.queries import application, enquiry, enrollment, provisioning

__all__ = ["application", "enquiry", "enrollment", "provisioning"]
