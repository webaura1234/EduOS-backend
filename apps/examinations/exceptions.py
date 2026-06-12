"""Examinations-specific API exceptions."""

from rest_framework.exceptions import APIException


class ExamFeeUnpaidError(APIException):
    """EC-EXAM-01 — hall ticket blocked until exam fee is paid."""

    status_code = 403
    default_detail = "Exam fee must be paid before generating a hall ticket."
    default_code = "exam_fee_unpaid"


class MarksVersionConflictError(APIException):
    """EC-CONCUR-02 — optimistic concurrency failure on marks PATCH."""

    status_code = 409
    default_detail = "Marks entry was modified by another user."
    default_code = "version_conflict"

    def __init__(self, *, current_version: int, current_value, detail=None):
        if detail is None:
            detail = {
                "message": self.default_detail,
                "currentVersion": current_version,
                "currentValue": current_value,
            }
        super().__init__(detail=detail)


class MarksConflictOfInterestError(APIException):
    """EC-GUARD-02 — faculty cannot mark linked child without override."""

    status_code = 403
    default_detail = "You cannot enter marks for a linked student account."
    default_code = "conflict_of_interest"


class MarksDeadlineError(APIException):
    """EC-FORM-05 — marks submission after deadline."""

    status_code = 403
    default_detail = "Marks submission deadline has passed."
    default_code = "marks_deadline_passed"


class ConfirmTokenRequiredError(APIException):
    """EC-EXAM-02 — publish requires a valid confirmToken from compute step."""

    status_code = 400
    default_detail = "A confirm token from the compute step is required to publish."
    default_code = "confirm_token_required"


class InvalidConfirmTokenError(APIException):
    """EC-EXAM-02 — confirm token missing, expired, or mismatched."""

    status_code = 400
    default_detail = "Invalid or expired publish confirmation token."
    default_code = "invalid_confirm_token"


class PublishJobInProgressError(APIException):
    """EC-CONCUR-01 — another publish job holds the exam lock."""

    status_code = 409
    default_detail = "Another publish operation is in progress for this exam."
    default_code = "job_in_progress"


class PublishedResultDeleteError(APIException):
    """EC-EXAM-03 — published results cannot be deleted; revise only."""

    status_code = 403
    default_detail = "Published results cannot be deleted. Use revise instead."
    default_code = "published_result_delete_forbidden"


class GraceMarksCollegeOnlyError(APIException):
    """EC-EXAM-07 — grace marks are college-only."""

    status_code = 403
    default_detail = "Grace marks are only available for colleges."
    default_code = "grace_marks_college_only"
