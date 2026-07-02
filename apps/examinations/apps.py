from django.apps import AppConfig


class ExaminationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.examinations"
    label = "examinations"
    verbose_name = "Examinations & Assignments"

    def ready(self):
        import apps.examinations.exports  # noqa: F401 — registers export definitions
