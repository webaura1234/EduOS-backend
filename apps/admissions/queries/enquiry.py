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


def list_enquiries(branch_id, *, status=None, statuses=None, source=None, created_after=None):
    qs = (
        Enquiry.objects.filter(branch_id=branch_id, is_active=True)
        .select_related("course")
        .select_related("application")
    )
    if status:
        qs = qs.filter(status=status)
    if statuses:
        qs = qs.filter(status__in=statuses)
    if source:
        qs = qs.filter(source=source)
    if created_after:
        qs = qs.filter(created_at__gte=created_after)
    return qs.order_by("-created_at")


def create_enquiry(*, branch, source, applicant_name, course=None, date_of_birth=None,
                   phone="", email="", captured_by=None, notes="", user=None,
                   custom_fields=None, is_public_submission=False) -> Enquiry:
    return Enquiry.objects.create(
        branch=branch, source=source, applicant_name=applicant_name, course=course,
        date_of_birth=date_of_birth, phone=phone, email=email, captured_by=captured_by,
        notes=notes, created_by=user, updated_by=user,
        custom_fields=custom_fields or {}, is_public_submission=is_public_submission,
    )


def update_enquiry(enquiry: Enquiry, fields: dict, user=None) -> Enquiry:
    for k, v in fields.items():
        setattr(enquiry, k, v)
    if user:
        enquiry.updated_by = user
    enquiry.save(update_fields=list(fields.keys()) + (["updated_by"] if user else []) + ["updated_at"])
    return enquiry


def funnel_counts(branch_id, *, from_date=None, to_date=None, status=None) -> dict:
    """Conversion funnel counts by enquiry source + status (F-078).

    Optional ``from_date`` / ``to_date`` scope by ``Enquiry.created_at`` (date).
    Optional ``status`` restricts to a single enquiry status before aggregating.
    """
    qs = Enquiry.objects.filter(branch_id=branch_id, is_active=True)
    if from_date is not None:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date is not None:
        qs = qs.filter(created_at__date__lte=to_date)
    if status:
        qs = qs.filter(status=status)
    by_source = {
        r["source"]: r["n"]
        for r in qs.values("source").annotate(n=Count("id"))
    }
    by_status = {
        r["status"]: r["n"]
        for r in qs.values("status").annotate(n=Count("id"))
    }
    return {"bySource": by_source, "byStatus": by_status}
