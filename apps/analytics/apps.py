from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.analytics"
    label = "analytics"
    verbose_name = "Analytics & Audit"

    def ready(self):
        import apps.analytics.exports  # noqa: F401 — registers aggregation report definitions
