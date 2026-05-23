from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Accounts & Auth"

    def ready(self):
        import apps.accounts.signals  # noqa: F401
