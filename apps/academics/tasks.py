"""Celery tasks for academics."""

from celery import shared_task

from apps.academics.interactors.rollover import _execute_rollover_sync
from apps.academics.models import RolloverRunStatus
from apps.academics.queries import rollover as rol_q


@shared_task(bind=True, max_retries=0)
def execute_rollover_task(self, run_id: str):
    """Background rollover commit for large student populations."""
    run = rol_q.get_run_by_id(run_id)
    if run is None:
        return {"error": "run_not_found"}

    branch = run.branch
    tenant = branch.tenant
    user = run.executed_by or run.created_by

    try:
        return _execute_rollover_sync(
            branch=branch,
            tenant=tenant,
            expected_version=run.preview_version,
            user=user,
            existing_run=run,
        )
    except Exception as exc:
        rol_q.update_rollover_run(
            run,
            {"status": RolloverRunStatus.FAILED, "error_message": str(exc)},
            user=user,
        )
        raise
