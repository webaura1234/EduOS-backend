from django.apps import AppConfig


class AdmissionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.admissions"
    label = "admissions"
    verbose_name = "Admissions"

    def ready(self):
        pass  # TODO: import apps.admissions.signals when created
