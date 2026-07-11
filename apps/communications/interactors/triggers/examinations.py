"""Examination notification triggers."""

from apps.accounts.models.profile import StudentProfile
from apps.communications.interactors.create import create_notification
from apps.communications.interactors.recipients import student_and_guardian_users


def notify_results_published(*, exam, branch, tenant, publication_id, student_results, user=None) -> int:
    count = 0
    exam_name = exam.name
    exam_id = str(exam.pk)
    for row in student_results:
        profile_id = row.get("studentId")
        student_name = row.get("studentName") or "Student"
        if not profile_id:
            continue
        try:
            profile = StudentProfile.objects.select_related("user").get(pk=profile_id)
        except StudentProfile.DoesNotExist:
            continue
        student_user = profile.user
        if not student_user or not student_user.is_active:
            continue
        for recipient, extras in student_and_guardian_users(student_user):
            if create_notification(
                "examination.results_published",
                tenant=tenant,
                branch=branch,
                recipient=recipient,
                variables={
                    "student_name": student_name,
                    "exam_name": exam_name,
                    "exam_id": exam_id,
                    **extras,
                },
                dedup_key=f"exam:published:{publication_id}:{profile_id}:{recipient.pk}",
                created_by=user,
                related_entity_type="exam",
                related_entity_id=exam.pk,
            ):
                count += 1
    return count
