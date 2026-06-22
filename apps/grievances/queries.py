"""Queries — Grievance reads/writes (all ORM here)."""

from django.utils import timezone

from apps.grievances.models import Grievance


def list_for_raiser(branch_id, raiser_user_id):
    return (
        Grievance.objects.filter(branch_id=branch_id, raised_by_id=raiser_user_id, is_active=True)
        .select_related("assigned_to", "raised_by", "student")
        .order_by("-created_at")
    )


def list_for_branch(branch_id, *, status=None):
    qs = (
        Grievance.objects.filter(branch_id=branch_id, is_active=True)
        .select_related("assigned_to", "raised_by", "student")
        .order_by("-created_at")
    )
    if status:
        qs = qs.filter(status=status)
    return qs


def get_in_branch(branch_id, grievance_id) -> Grievance | None:
    try:
        return Grievance.objects.select_related("assigned_to", "raised_by", "student").get(
            branch_id=branch_id, pk=grievance_id, is_active=True,
        )
    except (Grievance.DoesNotExist, ValueError, TypeError):
        return None


def create_grievance(*, branch, raised_by, raised_by_role, student, category,
                     subject, description, user=None) -> Grievance:
    return Grievance.objects.create(
        branch=branch, raised_by=raised_by, raised_by_role=raised_by_role, student=student,
        category=category, subject=subject, description=description,
        created_by=user, updated_by=user,
    )


def assign(grievance: Grievance, assignee_id, user=None) -> Grievance:
    grievance.assigned_to_id = assignee_id
    grievance.assigned_at = timezone.now()
    if grievance.status == "open":
        grievance.status = "in_review"
    grievance.updated_by = user
    grievance.save(update_fields=["assigned_to", "assigned_at", "status", "updated_by", "updated_at"])
    return grievance


def resolve(grievance: Grievance, *, resolution_note, status="resolved", user=None) -> Grievance:
    grievance.resolution_note = resolution_note
    grievance.status = status
    grievance.updated_by = user
    grievance.save(update_fields=["resolution_note", "status", "updated_by", "updated_at"])
    return grievance


def reopen(grievance: Grievance, user=None) -> Grievance:
    grievance.status = "in_review" if grievance.assigned_to_id else "open"
    grievance.updated_by = user
    grievance.save(update_fields=["status", "updated_by", "updated_at"])
    return grievance
