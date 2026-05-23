from django.apps import AppConfig


class FeesConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.fees"
    label = "fees"
    verbose_name = "Fees & Finance"

    def ready(self):
        pass  # TODO: import apps.fees.signals when created
