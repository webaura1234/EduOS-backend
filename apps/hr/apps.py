from django.apps import AppConfig


class HrConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.hr"
    label = "hr"
    verbose_name = "HR & Payroll"

    def ready(self):
        pass  # TODO: import apps.hr.signals when created
