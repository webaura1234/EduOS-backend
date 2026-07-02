from django.apps import AppConfig


class FeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fees"
    label = "fees"
    verbose_name = "Fees & Finance"

    def ready(self):
        import apps.fees.exports  # noqa: F401 — registers export definitions
