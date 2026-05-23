from django.apps import AppConfig


class CommunicationsConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.communications"
    label = "communications"
    verbose_name = "Communications"

    def ready(self):
        import apps.communications.signals  # noqa: F401
