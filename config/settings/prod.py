"""
Production settings — extends base.py.

Usage: DJANGO_SETTINGS_MODULE=config.settings.prod
"""

from .base import *  # noqa: F401, F403

DEBUG = False
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")  # noqa: F405

# ──────────────────────────────────────────────
# Security hardening
# ──────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

# ──────────────────────────────────────────────
# Database — read replica routing
# ──────────────────────────────────────────────
DATABASES["replica"] = {  # noqa: F405
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.environ.get("DB_REPLICA_NAME", os.environ.get("DB_NAME", "eduos")),  # noqa: F405
    "USER": os.environ.get("DB_REPLICA_USER", os.environ.get("DB_USER", "eduos")),  # noqa: F405
    "PASSWORD": os.environ.get("DB_REPLICA_PASSWORD", os.environ.get("DB_PASSWORD", "")),  # noqa: F405
    "HOST": os.environ.get("DB_REPLICA_HOST", os.environ.get("DB_HOST", "localhost")),  # noqa: F405
    "PORT": os.environ.get("DB_REPLICA_PORT", os.environ.get("DB_PORT", "5432")),  # noqa: F405
}

DATABASE_ROUTERS = ["apps.core.db_router.ReadReplicaRouter"]

# ──────────────────────────────────────────────
# Static files — served via CDN / S3
# ──────────────────────────────────────────────
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"

# ──────────────────────────────────────────────
# Logging — JSON structured for production
# ──────────────────────────────────────────────
LOGGING["handlers"]["console"]["formatter"] = "json"  # noqa: F405

# ──────────────────────────────────────────────
# Email — SMTP or SES for production
# ──────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")  # noqa: F405
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))  # noqa: F405
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")  # noqa: F405
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")  # noqa: F405
