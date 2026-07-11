from django.apps import AppConfig


class HrConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.hr"
    label = "hr"
    verbose_name = "HR & Payroll"

    def ready(self):
        import apps.hr.exports  # noqa: F401 — registers export definitions
