from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.core"
    label = "core"
    verbose_name = "Core"
