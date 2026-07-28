"""Attendance export definitions — self-service exports for faculty and students.

Registered on app startup via AttendanceConfig.ready(). Identity-scoping params
(facultyId / studentUserId) are set by the requesting view from request.user —
never trusted from client-supplied params — so a caller cannot read another
user's attendance by tampering with the request body.
"""

from apps.accounts.models.user import Role
from apps.analytics.enums import ReportType
from apps.core.exports.base import Column, ExportDefinition, FilterSpec
from apps.core.exports.registry import register


class FacultySubjectAttendanceExport(ExportDefinition):
    """Attendance records for the classes/subjects a faculty member teaches."""

    report_type = ReportType.FACULTY_SUBJECT_ATTENDANCE
    title = "My Subject Attendance"
    module = "attendance"
    description = "Attendance for classes you teach"
    allowed_roles = [Role.FACULTY]
    formats = ["csv"]
    sync_threshold = 500
    estimated_runtime = "instant"
    filters = [
        FilterSpec("fromDate", "From Date", type="date", group="criteria"),
        FilterSpec("toDate", "To Date", type="date", group="criteria"),
    ]

    def get_queryset(self, *, tenant_id, branch_id, params: dict):
        from apps.academics.models import BatchFaculty
        from apps.attendance.models import AttendanceRecord

        faculty_id = params.get("facultyId")
        batch_subject_ids = BatchFaculty.objects.filter(
            faculty_id=faculty_id, is_active=True,
            batch_subject__batch__course__department__branch__tenant_id=tenant_id,
        ).values_list("batch_subject_id", flat=True)

        qs = AttendanceRecord.objects.filter(
            session__batch_subject_id__in=batch_subject_ids, is_active=True,
        )
        if branch_id:
            qs = qs.filter(session__branch_id=branch_id)
        if params.get("fromDate"):
            qs = qs.filter(session__date__gte=params["fromDate"])
        if params.get("toDate"):
            qs = qs.filter(session__date__lte=params["toDate"])
        return qs.select_related(
            "student__student_profile__user", "session", "session__batch_subject__subject",
        ).order_by("session__date")

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("date", "Date", format="date"),
            Column("subject", "Subject"),
            Column("student_name", "Student Name"),
            Column("status", "Status"),
        ]

    def get_row(self, record) -> dict:
        subject_name = ""
        try:
            subject_name = record.session.batch_subject.subject.name
        except Exception:  # noqa: BLE001
            pass
        student_name = ""
        try:
            student_name = record.student.user.full_name
        except Exception:  # noqa: BLE001
            pass
        return {
            "date": record.session.date.isoformat() if record.session and record.session.date else "",
            "subject": subject_name,
            "student_name": student_name,
            "status": record.get_status_display(),
        }

    def get_filename(self, params: dict) -> str:
        return "my-subject-attendance"


class StudentAttendanceExport(ExportDefinition):
    """A student's own attendance records, any date range."""

    report_type = ReportType.STUDENT_ATTENDANCE
    title = "My Attendance"
    module = "attendance"
    description = "Your attendance records"
    allowed_roles = [Role.STUDENT]
    formats = ["csv"]
    sync_threshold = 2000
    estimated_runtime = "instant"
    filters = [
        FilterSpec("fromDate", "From Date", type="date", group="criteria"),
        FilterSpec("toDate", "To Date", type="date", group="criteria"),
    ]

    def get_queryset(self, *, tenant_id, branch_id, params: dict):
        from apps.attendance.models import AttendanceRecord

        enrollment_id = params.get("enrollmentId")
        qs = AttendanceRecord.objects.filter(student_id=enrollment_id, is_active=True)
        if params.get("fromDate"):
            qs = qs.filter(session__date__gte=params["fromDate"])
        if params.get("toDate"):
            qs = qs.filter(session__date__lte=params["toDate"])
        return qs.select_related("session", "session__batch_subject__subject").order_by("session__date")

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("date", "Date", format="date"),
            Column("subject", "Subject"),
            Column("status", "Status"),
        ]

    def get_row(self, record) -> dict:
        subject_name = ""
        try:
            subject_name = record.session.batch_subject.subject.name
        except Exception:  # noqa: BLE001
            pass
        return {
            "date": record.session.date.isoformat() if record.session and record.session.date else "",
            "subject": subject_name or "All day",
            "status": record.get_status_display(),
        }

    def get_filename(self, params: dict) -> str:
        return "my-attendance"


def register_all() -> None:
    register(FacultySubjectAttendanceExport())
    register(StudentAttendanceExport())


register_all()
