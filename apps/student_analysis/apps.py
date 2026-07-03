from django.apps import AppConfig


class StudentAnalysisConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.student_analysis"
    label = "student_analysis"
    verbose_name = "Student Analysis"

    def ready(self):
        pass
