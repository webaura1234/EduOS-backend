"""Celery task — apply a queued student import job."""

from celery import shared_task


@shared_task(bind=True, max_retries=0, soft_time_limit=60 * 30, time_limit=60 * 35)
def run_student_import_job(self, job_id: str):
    from apps.admissions.imports.runner import execute_import_job

    execute_import_job(job_id=job_id, celery_task_id=getattr(self.request, "id", "") or "")
