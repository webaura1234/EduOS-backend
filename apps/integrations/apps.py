from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.integrations"
    label = "integrations"
    verbose_name = "Integrations"

    def ready(self):
        import apps.integrations.signals  # noqa: F401
