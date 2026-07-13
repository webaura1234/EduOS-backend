"""Academics API exceptions."""

from rest_framework.exceptions import APIException

PROMOTION_WORKSPACE_PATH = "/admin/academic-management/promotion"


class PromotionExecutionInProgressError(APIException):
    """Raised when a branch already has an active promotion execution."""

    status_code = 409
    default_detail = "Another promotion is already in progress."
    default_code = "promotion_execution_in_progress"

    def __init__(self, *, running_session_id, run_id: str | None = None):
        detail = {
            "code": self.default_code,
            "detail": self.default_detail,
            "runningSessionId": str(running_session_id),
        }
        if run_id:
            detail["runId"] = run_id
        super().__init__(detail)


class RolloverDirectExecutionDisabledError(APIException):
    """Standalone rollover was retired; promotion is the sole execution path."""

    status_code = 410
    default_detail = (
        "Standalone academic year rollover is no longer available. "
        "Use Academic Year Promotion to execute the year-end transition."
    )
    default_code = "rollover_direct_execution_disabled"

    def __init__(self):
        super().__init__(
            {
                "code": self.default_code,
                "detail": self.default_detail,
                "promotionPath": PROMOTION_WORKSPACE_PATH,
            }
        )
