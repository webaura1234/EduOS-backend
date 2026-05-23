"""
ASGI config for EduOS project.

Supports HTTP + WebSocket (Django Channels) for real-time
attendance dashboard and notification badges.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_asgi_application()
