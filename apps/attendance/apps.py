from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "apps.attendance"
    label = "attendance"
    verbose_name = "Attendance"

    def ready(self):
        import apps.attendance.signals  # noqa: F401
