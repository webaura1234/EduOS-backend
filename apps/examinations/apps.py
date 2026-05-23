from django.apps import AppConfig


class ExaminationsConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.examinations"
    label = "examinations"
    verbose_name = "Examinations & Assignments"

    def ready(self):
        import apps.examinations.signals  # noqa: F401
