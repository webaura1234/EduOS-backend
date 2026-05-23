from django.apps import AppConfig


class HrConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.hr"
    label = "hr"
    verbose_name = "HR & Payroll"

    def ready(self):
        import apps.hr.signals  # noqa: F401
