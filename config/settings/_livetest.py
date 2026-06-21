"""TEMPORARY settings for a local auth smoke test (SQLite on /tmp). Safe to delete."""

from .dev import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/tmp/eduos_live.sqlite3",
        "ATOMIC_REQUESTS": True,
    }
}
DEBUG = True
ALLOWED_HOSTS = ["*"]
