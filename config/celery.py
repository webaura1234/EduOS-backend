"""
Celery configuration for EduOS.

Handles background tasks: exports, notifications, payroll,
reconciliation, rollover, data integrity checks.
"""

import os

from celery import Celery

from config.env import load_env

load_env()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("eduos")

# Read config from Django settings, namespace CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to verify Celery is working."""
    print(f"Request: {self.request!r}")
