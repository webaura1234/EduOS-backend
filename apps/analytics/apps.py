from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.analytics"
    label = "analytics"
    verbose_name = "Analytics & Audit"

    def ready(self):
        import apps.analytics.signals  # noqa: F401
