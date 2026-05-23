from django.apps import AppConfig


class AdmissionsConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.admissions"
    label = "admissions"
    verbose_name = "Admissions"

    def ready(self):
        import apps.admissions.signals  # noqa: F401
