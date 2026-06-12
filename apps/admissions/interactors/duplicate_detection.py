"""Interactors — duplicate detection and sibling override (F-080 / EC-DATA-03 / EC-GUARD-06)."""

import uuid
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.admissions.queries import enrollment as enr_q
from apps.admissions.queries import provisioning as prov_q


def detect_duplicates(*, branch_id, first_name, last_name, date_of_birth, phone):
    full_name = f"{first_name} {last_name}".strip()
    return prov_q.find_duplicate_students(
        branch_id, name=full_name, date_of_birth=date_of_birth, phone=phone
    )


@transaction.atomic
def resolve_sibling_group_id(*, branch_id, sibling_student_profile_id, user=None):
    """
    Resolve or generate a sibling group ID for twins/siblings during duplicate override.
    If the sibling student already has an enrollment with a sibling_group_id, reuse it.
    Otherwise, generate a new one, update the sibling's active enrollment, and return it.
    """
    sibling_enrollment = enr_q.get_active_enrollment_for_profile(sibling_student_profile_id)
    if not sibling_enrollment:
        raise ValidationError({"siblingStudentProfileId": "Active enrollment for the sibling student was not found."})
        
    if sibling_enrollment.sibling_group_id:
        return sibling_enrollment.sibling_group_id
        
    # Generate new UUID
    new_group_id = uuid.uuid4()
    enr_q.update_enrollment(sibling_enrollment, {"sibling_group_id": new_group_id}, user=user)
    return new_group_id
