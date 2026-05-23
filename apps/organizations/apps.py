from django.apps import AppConfig


class OrganizationsConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.organizations"
    label = "organizations"
    verbose_name = "Organizations & Tenancy"

    def ready(self):
        import apps.organizations.signals  # noqa: F401
