"""Queries — Enquiry (all ORM here)."""

from django.db.models import Count

from apps.admissions.models import Enquiry


def get_enquiry(branch_id, enquiry_id) -> Enquiry | None:
    try:
        return Enquiry.objects.select_related("course").get(
            branch_id=branch_id, pk=enquiry_id, is_active=True
        )
    except (Enquiry.DoesNotExist, ValueError, TypeError):
        return None


def list_enquiries(branch_id, *, status=None, source=None):
    qs = Enquiry.objects.filter(branch_id=branch_id, is_active=True).select_related("course")
    if status:
        qs = qs.filter(status=status)
    if source:
        qs = qs.filter(source=source)
    return qs.order_by("-created_at")


def create_enquiry(*, branch, source, applicant_name, course=None, date_of_birth=None,
                   phone="", email="", captured_by=None, notes="", user=None) -> Enquiry:
    return Enquiry.objects.create(
        branch=branch, source=source, applicant_name=applicant_name, course=course,
        date_of_birth=date_of_birth, phone=phone, email=email, captured_by=captured_by,
        notes=notes, created_by=user, updated_by=user,
    )


def update_enquiry(enquiry: Enquiry, fields: dict, user=None) -> Enquiry:
    for k, v in fields.items():
        setattr(enquiry, k, v)
    if user:
        enquiry.updated_by = user
    enquiry.save(update_fields=list(fields.keys()) + (["updated_by"] if user else []) + ["updated_at"])
    return enquiry


def funnel_counts(branch_id) -> dict:
    """Conversion funnel counts by enquiry source + status (F-078)."""
    by_source = {
        r["source"]: r["n"]
        for r in Enquiry.objects.filter(branch_id=branch_id, is_active=True)
        .values("source").annotate(n=Count("id"))
    }
    by_status = {
        r["status"]: r["n"]
        for r in Enquiry.objects.filter(branch_id=branch_id, is_active=True)
        .values("status").annotate(n=Count("id"))
    }
    return {"bySource": by_source, "byStatus": by_status}
