from django.apps import AppConfig


class ExaminationsConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.examinations"
    label = "examinations"
    verbose_name = "Examinations & Assignments"

    def ready(self):
        pass  # TODO: import apps.examinations.signals when created
