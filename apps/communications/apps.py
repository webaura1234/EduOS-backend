from django.apps import AppConfig


class CommunicationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.communications"
    label = "communications"
    verbose_name = "Communications"

    def ready(self):
        pass  # TODO: import apps.communications.signals when created
