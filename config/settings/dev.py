"""
Development settings — extends base.py.

Usage: DJANGO_SETTINGS_MODULE=config.settings.dev
"""

from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# ──────────────────────────────────────────────
# CSRF — allow admin/API from localhost and 127.0.0.1 (use one host consistently)
# ──────────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_extra_csrf = os.environ.get("CSRF_TRUSTED_ORIGINS", "")
if _extra_csrf:
    CSRF_TRUSTED_ORIGINS.extend(
        origin.strip() for origin in _extra_csrf.split(",") if origin.strip()
    )

# ──────────────────────────────────────────────
# Database — SQLite by default locally; Postgres via docker (USE_POSTGRES=true)
# ──────────────────────────────────────────────
_use_postgres = os.environ.get("USE_POSTGRES", "").lower() in ("1", "true", "yes")
# Back-compat: USE_SQLITE=false explicitly opts into Postgres
if os.environ.get("USE_SQLITE", "").lower() in ("0", "false", "no"):
    _use_postgres = True

if _use_postgres:
    DATABASES["default"]["NAME"] = os.environ.get("DB_NAME", "eduos_dev")  # noqa: F405
    DATABASES["default"]["USER"] = os.environ.get("DB_USER", "eduos")  # noqa: F405
    DATABASES["default"]["PASSWORD"] = os.environ.get("DB_PASSWORD", "")  # noqa: F405
    DATABASES["default"]["HOST"] = os.environ.get("DB_HOST", "localhost")  # noqa: F405
    DATABASES["default"]["PORT"] = os.environ.get("DB_PORT", "5432")  # noqa: F405
    # SSL options for cloud-hosted Postgres (e.g. Neon DB)
    _sslmode = os.environ.get("DB_SSLMODE", "require")
    if _sslmode and _sslmode != "disable":
        DATABASES["default"].setdefault("OPTIONS", {})  # noqa: F405
        DATABASES["default"]["OPTIONS"]["sslmode"] = _sslmode
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "ATOMIC_REQUESTS": True,
        }
    }

# ──────────────────────────────────────────────
# Cache — locmem by default (no Redis required). Set USE_REDIS=true to use Redis.
# ──────────────────────────────────────────────
_use_redis = os.environ.get("USE_REDIS", "").lower() in ("1", "true", "yes")
if not _use_redis:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "unique-snowflake-dev",
        }
    }

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
# Debug toolbar is disabled in dev by default to prevent missing 'djdt' namespace url conflicts.
pass
