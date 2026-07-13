"""Celery tasks for academics."""

from celery import shared_task
from django.utils import timezone

from apps.academics.models.promotion import PromotionExecutionStatus
from apps.academics.queries import promotion_execution as exec_q
from apps.academics.queries import promotion_preparation as prep_q


@shared_task(bind=True, max_retries=0)
def execute_rollover_task(self, run_id: str):
    """Background rollover commit for large student populations (retired)."""
    from apps.academics.exceptions import RolloverDirectExecutionDisabledError

    raise RolloverDirectExecutionDisabledError()


@shared_task(bind=True, max_retries=0)
def execute_promotion_task(self, run_id: str):
    """Background promotion execution."""
    from apps.academics.interactors import promotion_execution as exec_i

    run = exec_q.get_run_by_id(run_id)
    if run is None:
        return {"error": "run_not_found"}
    user = run.executed_by or run.created_by
    try:
        return exec_i.run_execution(run_id=run_id, user=user)
    except Exception as exc:
        exec_q.update_run(
            run,
            {
                "status": PromotionExecutionStatus.FAILED,
                "error_message": str(exc),
                "completed_at": timezone.now(),
            },
            user=user,
        )
        prep_q.update_session(
            run.session,
            {"execution_status": PromotionExecutionStatus.FAILED},
            user=user,
        )
        raise
