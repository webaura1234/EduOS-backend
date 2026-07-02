from django.apps import AppConfig


class AttendanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.attendance"
    label = "attendance"
    verbose_name = "Attendance"

    def ready(self):
        import apps.attendance.exports  # noqa: F401 — registers export definitions
