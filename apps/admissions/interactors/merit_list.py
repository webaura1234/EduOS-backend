"""Interactors — merit list and waitlist management (F-075/F-084)."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.admissions.enums import ApplicationStatus
from apps.admissions.queries import application as app_q


def get_merit_list(*, branch_id, course_id):
    """
    Return a ranked list of applications for a course (submitted, under_review, waitlisted).
    Sorted by eligibility score (if present) descending, then by created_at ascending (earlier first).
    """
    apps = app_q.ranked_applications_for_course(branch_id, course_id)
    return sorted(
        apps,
        key=lambda a: (
            float(a.eligibility_result.get("score") or 0.0) if a.eligibility_result else 0.0,
            -a.created_at.timestamp()
        ),
        reverse=True
    )


@transaction.atomic
def add_to_waitlist(*, branch, application, rank, user=None):
    """Add an application to the waitlist at the given rank (F-084)."""
    if application.status == ApplicationStatus.ENROLLED:
        raise ValidationError({"application": "Cannot waitlist an enrolled application."})
    
    app_q.update_application(application, {"status": ApplicationStatus.WAITLISTED}, user=user)
    return app_q.upsert_waitlist(
        branch=branch, application=application, course=application.course, rank=rank, user=user
    )


@transaction.atomic
def promote_waitlist_entry(*, branch_id, waitlist_entry_id, user=None):
    """
    Promote an application from the waitlist to ACCEPTED status (F-084).
    Deletes the waitlist entry and decrements the rank of subsequent waitlist entries.
    """
    entry = app_q.get_waitlist_entry(branch_id, waitlist_entry_id)
    if not entry:
        raise ValidationError({"waitlist": "Waitlist entry not found."})
    
    application = entry.application
    course = entry.course
    rank = entry.rank
    
    # Update application status to ACCEPTED
    app_q.update_application(application, {"status": ApplicationStatus.ACCEPTED}, user=user)
    
    # Delete waitlist entry
    app_q.delete_waitlist_entry(entry)
    
    # Shift ranks of other waitlist entries for this course down by 1
    app_q.decrement_waitlist_ranks(course.pk, rank)
    
    return application
