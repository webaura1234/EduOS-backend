"""Admissions notification triggers."""

from apps.accounts.models.user import Role, User
from apps.communications.interactors.create import create_notification


def notify_application_status_updated(*, application, new_status, user=None) -> int:
    branch = application.branch
    applicant_name = "Applicant"
    if application.enquiry_id:
        from apps.admissions.models import Enquiry
        try:
            enquiry = Enquiry.objects.get(pk=application.enquiry_id)
            applicant_name = enquiry.applicant_name or applicant_name
        except Enquiry.DoesNotExist:
            pass

    app_number = str(application.pk)[:8].upper()
    count = 0
    admins = User.objects.filter(
        branch_id=branch.pk, role__in=(Role.ADMIN, Role.SUPER_ADMIN), is_active=True,
    )
    for admin in admins:
        if create_notification(
            "admissions.status_updated",
            tenant=branch.tenant,
            branch=branch,
            recipient=admin,
            variables={
                "applicant_name": applicant_name,
                "application_number": app_number,
                "new_status": new_status,
                "application_id": str(application.pk),
                "child_id": "",
            },
            dedup_key=f"adm:status:{application.pk}:{new_status}:{admin.pk}",
            created_by=user,
            related_entity_type="application",
            related_entity_id=application.pk,
        ):
            count += 1
    return count
