from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.academics"
    label = "academics"
    verbose_name = "Academics"

    def ready(self):
        import apps.academics.signals  # noqa: F401
