"""
Development settings — extends base.py.

Usage: DJANGO_SETTINGS_MODULE=config.settings.dev
"""

from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# ──────────────────────────────────────────────
# Database — local PostgreSQL
# ──────────────────────────────────────────────
DATABASES["default"]["NAME"] = os.environ.get("DB_NAME", "eduos_dev")  # noqa: F405

# ──────────────────────────────────────────────
# CORS — allow all in dev
# ──────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True

# ──────────────────────────────────────────────
# Email — console backend for dev
# ──────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ──────────────────────────────────────────────
# Celery — eager execution in dev (synchronous)
# ──────────────────────────────────────────────
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ──────────────────────────────────────────────
# Debug toolbar (optional)
# ──────────────────────────────────────────────
try:
    import debug_toolbar  # noqa: F401

    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
    INTERNAL_IPS = ["127.0.0.1"]
except ImportError:
    pass
