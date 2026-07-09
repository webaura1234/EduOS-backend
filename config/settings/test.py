from .base import *

# Suppress real MSG91 calls — email.py and sms.py skip the network in DEBUG mode.
DEBUG = True

# Use SQLite in-memory database for fast testing without needing PostgreSQL service
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Speed up password hashing in tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable Celery asynchronous tasks, execute synchronously
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable caches or use local memory cache for testing
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}

# Never let tests hit real S3/R2, regardless of what the local .env has configured
# for live development — tests must be hermetic.
S3_MODE = "sandbox"
R2_PUBLIC_BASE_URL = ""

# Rate limits share a process-wide cache; disable in tests so auth endpoint
# suites are not flaky when many login/OTP requests run in one session.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": [],
}
