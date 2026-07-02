"""Examinations export definitions — self-service exports for faculty and students.

Registered on app startup via ExaminationsConfig.ready(). Identity-scoping params
(facultyId / studentUserId) are set by the requesting view from request.user —
never trusted from client-supplied params.
"""

from apps.accounts.models.user import Role
from apps.analytics.enums import ReportType
from apps.core.exports.base import Column, ExportDefinition
from apps.core.exports.registry import register


class FacultyClassResultsExport(ExportDefinition):
    """Marks a faculty member has entered for the subjects they teach."""

    report_type = ReportType.FACULTY_CLASS_RESULTS
    title = "My Class Results"
    allowed_roles = [Role.FACULTY]
    formats = ["csv"]
    sync_threshold = 500

    def get_queryset(self, *, tenant_id, branch_id, params: dict):
        from apps.academics.models import BatchFaculty
        from apps.examinations.models.results import MarksEntry

        faculty_id = params.get("facultyId")
        batch_subject_ids = BatchFaculty.objects.filter(
            faculty_id=faculty_id, is_active=True,
            batch_subject__batch__course__department__branch__tenant_id=tenant_id,
        ).values_list("batch_subject_id", flat=True)
        subject_ids = BatchFaculty.objects.filter(
            faculty_id=faculty_id, is_active=True,
        ).values_list("batch_subject__subject_id", flat=True)

        qs = MarksEntry.objects.filter(
            subject_id__in=subject_ids, is_active=True,
            exam__branch__tenant_id=tenant_id,
        )
        if branch_id:
            qs = qs.filter(exam__branch_id=branch_id)
        if params.get("examId"):
            qs = qs.filter(exam_id=params["examId"])
        return qs.select_related(
            "exam", "subject", "student__student_profile__user",
        ).order_by("-exam__created_at", "student__student_profile__user__first_name")

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("exam", "Exam"),
            Column("subject", "Subject"),
            Column("student_name", "Student Name"),
            Column("marks", "Marks", format="number"),
            Column("is_absent", "Absent"),
            Column("status", "Status"),
        ]

    def get_row(self, entry) -> dict:
        student_name = ""
        try:
            student_name = entry.student.user.full_name
        except Exception:  # noqa: BLE001
            pass
        return {
            "exam": entry.exam.name,
            "subject": entry.subject.name,
            "student_name": student_name,
            "marks": float(entry.marks) if entry.marks is not None else "",
            "is_absent": "Yes" if entry.is_absent else "No",
            "status": entry.get_marks_status_display(),
        }

    def get_filename(self, params: dict) -> str:
        return "my-class-results"


class StudentExamResultsExport(ExportDefinition):
    """A student's own published exam results (aggregated per exam)."""

    report_type = ReportType.STUDENT_EXAM_RESULTS
    title = "My Exam Results"
    allowed_roles = [Role.STUDENT]
    formats = ["csv"]
    sync_threshold = 500

    def get_queryset(self, *, tenant_id, branch_id, params: dict):
        from apps.examinations.models.results import StudentResult

        enrollment_id = params.get("enrollmentId")
        qs = StudentResult.objects.filter(
            student_id=enrollment_id, is_active=True,
            publication__isnull=False,  # only published results
            exam__branch__tenant_id=tenant_id,
        )
        return qs.select_related("exam").order_by("-exam__created_at")

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("exam", "Exam"),
            Column("total_marks", "Total Marks", format="number"),
            Column("percentage", "Percentage", format="number"),
            Column("grade", "Grade"),
            Column("gpa", "GPA", format="number"),
            Column("is_pass", "Result"),
        ]

    def get_row(self, result) -> dict:
        return {
            "exam": result.exam.name,
            "total_marks": float(result.total_marks),
            "percentage": float(result.percentage),
            "grade": result.grade,
            "gpa": float(result.gpa) if result.gpa is not None else "",
            "is_pass": "Pass" if result.is_pass else "Fail",
        }

    def get_filename(self, params: dict) -> str:
        return "my-exam-results"


def register_all() -> None:
    register(FacultyClassResultsExport())
    register(StudentExamResultsExport())


register_all()
