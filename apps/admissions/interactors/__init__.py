"""Admissions interactors."""

from apps.admissions.interactors.application import (
    add_application_document,
    reject_application,
    save_application_step,
    verify_document,
)
from apps.admissions.interactors.duplicate_detection import (
    detect_duplicates,
    resolve_sibling_group_id,
)
from apps.admissions.interactors.enquiry import (
    capture_enquiry,
    convert_enquiry_to_application,
)
from apps.admissions.interactors.enrollment import (
    DuplicateStudentError,
    LinkedAccountWarning,
    ProvisionEnrollmentInteractor,
    transfer_enrollment,
)
from apps.admissions.interactors.merit_list import (
    add_to_waitlist,
    get_merit_list,
    promote_waitlist_entry,
)

__all__ = [
    "capture_enquiry",
    "convert_enquiry_to_application",
    "save_application_step",
    "add_application_document",
    "verify_document",
    "reject_application",
    "detect_duplicates",
    "resolve_sibling_group_id",
    "get_merit_list",
    "add_to_waitlist",
    "promote_waitlist_entry",
    "ProvisionEnrollmentInteractor",
    "transfer_enrollment",
    "DuplicateStudentError",
    "LinkedAccountWarning",
]
