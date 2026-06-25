"""Queries — Application, ApplicationDocument, Waitlist (all ORM here)."""

from django.db.models import Prefetch

from apps.admissions.models import Application, ApplicationDocument, StudentEnrollment, Waitlist


def get_application(branch_id, application_id) -> Application | None:
    try:
        return Application.objects.select_related("enquiry", "course").get(
            branch_id=branch_id, pk=application_id, is_active=True
        )
    except (Application.DoesNotExist, ValueError, TypeError):
        return None


def list_applications(branch_id, *, status=None, course_id=None):
    qs = (
        Application.objects.filter(branch_id=branch_id, is_active=True)
        .select_related("enquiry", "course", "waitlist_entry")
        .prefetch_related(
            Prefetch(
                "documents",
                queryset=ApplicationDocument.objects.filter(is_active=True),
                to_attr="active_documents",
            ),
            Prefetch(
                "enrollments",
                queryset=StudentEnrollment.objects.filter(is_active=True).select_related("student_profile"),
                to_attr="active_enrollments",
            ),
        )
    )
    if status:
        qs = qs.filter(status=status)
    if course_id:
        qs = qs.filter(course_id=course_id)
    return qs.order_by("-created_at")


def create_application(*, branch, enquiry, course=None, status="draft", step=None, user=None) -> Application:
    return Application.objects.create(
        branch=branch, enquiry=enquiry, course=course, status=status, step=step or {},
        created_by=user, updated_by=user,
    )


def update_application(application: Application, fields: dict, user=None) -> Application:
    for k, v in fields.items():
        setattr(application, k, v)
    if user:
        application.updated_by = user
    application.save(update_fields=list(fields.keys()) + (["updated_by"] if user else []) + ["updated_at"])
    return application


def add_document(*, application, doc_type, s3_key="", user=None) -> ApplicationDocument:
    return ApplicationDocument.objects.create(
        application=application, doc_type=doc_type, s3_key=s3_key,
        created_by=user, updated_by=user,
    )


def get_document(branch_id, document_id) -> ApplicationDocument | None:
    try:
        return ApplicationDocument.objects.select_related("application").get(
            application__branch_id=branch_id, pk=document_id, is_active=True
        )
    except (ApplicationDocument.DoesNotExist, ValueError, TypeError):
        return None


def update_document(document: ApplicationDocument, fields: dict, user=None) -> ApplicationDocument:
    for k, v in fields.items():
        setattr(document, k, v)
    if user:
        document.updated_by = user
    document.save(update_fields=list(fields.keys()) + (["updated_by"] if user else []) + ["updated_at"])
    return document


# ── Merit list / waitlist ─────────────────────────────────────────────────────
def ranked_applications_for_course(branch_id, course_id):
    """Applications for a course ordered for merit ranking (submitted/under-review)."""
    return Application.objects.filter(
        branch_id=branch_id, course_id=course_id, is_active=True,
        status__in=["submitted", "under_review", "waitlisted"],
    ).select_related("enquiry").order_by("created_at")


def upsert_waitlist(*, branch, application, course, rank, user=None) -> Waitlist:
    entry, _ = Waitlist.objects.update_or_create(
        application=application,
        defaults=dict(branch=branch, course=course, rank=rank, is_active=True,
                      created_by=user, updated_by=user),
    )
    return entry


def get_waitlist_entry(branch_id, waitlist_id) -> Waitlist | None:
    try:
        return Waitlist.objects.select_related("application", "course").get(
            branch_id=branch_id, pk=waitlist_id, is_active=True
        )
    except (Waitlist.DoesNotExist, ValueError, TypeError):
        return None


def list_waitlist(branch_id, course_id=None):
    qs = Waitlist.objects.filter(branch_id=branch_id, is_active=True).select_related(
        "application", "course"
    )
    if course_id:
        qs = qs.filter(course_id=course_id)
    return qs.order_by("rank")


def delete_waitlist_entry(entry: Waitlist):
    """Hard delete waitlist entry to free the rank unique constraint."""
    entry.delete()


def decrement_waitlist_ranks(course_id, above_rank):
    """Decrement rank for all active waitlist entries of a course with rank > above_rank."""
    from django.db.models import F
    Waitlist.objects.filter(course_id=course_id, rank__gt=above_rank, is_active=True).update(rank=F("rank") - 1)

