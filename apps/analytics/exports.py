"""Aggregation-style report definitions — registered on analytics app startup."""

import datetime

from django.utils import timezone

from apps.accounts.models.user import Role
from apps.admissions.queries.enquiry import funnel_counts
from apps.analytics.enums import ReportType
from apps.attendance.interactors import report as att_report
from apps.core.exports.base import ACADEMIC_YEAR_FILTER, BATCH_FILTER, AggregationExportDefinition, Column, FilterSpec
from apps.core.exports.filters import enquiry_status_filter, leave_status_filter
from apps.core.exports.registry import register
from apps.core.exports.year import resolve_report_year, year_include_inactive


def _parse_date(value, default):
    if not value:
        return default
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def _year_scope(params, branch):
    year = resolve_report_year(params, branch)
    return year, year_include_inactive(year)


class AdmissionFunnelExport(AggregationExportDefinition):
    report_type = ReportType.ADMISSION_FUNNEL
    title = "Admissions Funnel"
    module = "admissions"
    description = "Enquiries through enrollment by stage"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    supports_preview = True
    supports_search = True
    estimated_runtime = "instant"
    sync_threshold = 500
    filters = [ACADEMIC_YEAR_FILTER, enquiry_status_filter()]

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("stage", "Stage"),
            Column("students", "Students", format="number"),
            Column("conversion", "Conversion %", format="number"),
            Column("dropoffs", "Drop-offs", format="number"),
        ]

    def resolve_rows(self, *, tenant, branch, params: dict) -> list[dict]:
        from apps.admissions.enums import EnquiryStatus

        year = resolve_report_year(params, branch)
        f = funnel_counts(
            branch.pk,
            from_date=year.start_date,
            to_date=year.end_date,
            status=params.get("status") or None,
        )
        by_status = f.get("byStatus", {})

        stages = [
            (EnquiryStatus.NEW, "New Enquiries"),
            (EnquiryStatus.CONTACTED, "Contacted"),
            (EnquiryStatus.CONVERTED, "Converted"),
            (EnquiryStatus.LOST, "Lost"),
        ]

        rows = []
        prev_count = 0

        for enum_val, label in stages:
            count = by_status.get(enum_val, 0)

            if not rows:
                conversion = 100.0 if count > 0 else 0.0
                dropoffs = 0
            else:
                conversion = round((count / prev_count * 100), 2) if prev_count > 0 else 0.0
                dropoffs = prev_count - count if prev_count > count else 0

            rows.append({
                "stage": label,
                "students": count,
                "conversion": conversion,
                "dropoffs": dropoffs,
            })
            prev_count = max(prev_count, count)

        return rows


class HrLeaveSummaryExport(AggregationExportDefinition):
    report_type = ReportType.HR_LEAVE_SUMMARY
    title = "HR Leave Summary"
    module = "hr"
    description = "Leave balances and usage by employee"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    supports_preview = True
    estimated_runtime = "instant"
    sync_threshold = 500
    filters = [ACADEMIC_YEAR_FILTER, leave_status_filter()]

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("employeeCode", "Employee ID"),
            Column("name", "Employee Name"),
            Column("designation", "Designation"),
            Column("leave_type", "Leave Type"),
            Column("balance", "Leave Balance", format="number"),
            Column("used", "Leave Used", format="number"),
        ]

    def resolve_rows(self, *, tenant, branch, params: dict) -> list[dict]:
        from apps.hr.models.employee import Employee
        from apps.hr.enums import LeaveStatus

        year = resolve_report_year(params, branch)
        year_start, year_end = year.start_date, year.end_date
        status_filter = params.get("status") or LeaveStatus.APPROVED

        employees = (
            Employee.objects.filter(branch=branch, is_active=True)
            .select_related("user")
            .prefetch_related("leave_balances", "leave_applications")
        )

        rows = []
        for emp in employees:
            used_by_type = {}
            for app in emp.leave_applications.all():
                if not app.is_active or app.status != status_filter:
                    continue
                if app.to_date < year_start or app.from_date > year_end:
                    continue
                used_by_type[app.leave_type] = used_by_type.get(app.leave_type, 0) + float(app.days)

            for bal in emp.leave_balances.all():
                leave_type = bal.leave_type
                used = used_by_type.get(leave_type, 0)
                rows.append({
                    "employeeCode": emp.employee_code,
                    "name": emp.user.full_name if emp.user else "",
                    "designation": emp.designation or "",
                    "leave_type": bal.get_leave_type_display(),
                    "balance": float(bal.balance_days),
                    "used": used,
                })

        return rows


class AttendanceMonthlyExport(AggregationExportDefinition):
    report_type = ReportType.ATTENDANCE_MONTHLY
    title = "Attendance Monthly"
    module = "attendance"
    description = "Per-student attendance for a calendar month"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    supports_preview = True
    estimated_runtime = "instant"
    sync_threshold = 500
    filters = [
        ACADEMIC_YEAR_FILTER,
        FilterSpec("year", "Calendar year", type="number", required=True, group="criteria"),
        FilterSpec("month", "Month", type="number", required=True, group="criteria"),
        BATCH_FILTER,
    ]

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("admissionNo", "Admission No"),
            Column("name", "Student Name"),
            Column("class", "Class"),
            Column("section", "Section"),
            Column("academicYear", "Academic Year"),
            Column("sessions", "Working Days", format="number"),
            Column("present", "Present Days", format="number"),
            Column("absent", "Absent Days", format="number"),
            Column("percent", "Attendance %", format="number"),
            Column("status", "Status"),
            Column("teacher", "Class Teacher"),
            Column("branchName", "Branch"),
            Column("generatedDate", "Generated Date", format="date"),
        ]

    def resolve_rows(self, *, tenant, branch, params: dict) -> list[dict]:
        year_obj, include_inactive = _year_scope(params, branch)
        year = int(params.get("year", timezone.now().year))
        month = int(params.get("month", timezone.now().month))
        rows = att_report.monthly_report(
            branch,
            year=year,
            month=month,
            batch_id=params.get("batchId"),
            academic_year_id=year_obj.pk,
            include_inactive=include_inactive,
        )["rows"]
        gen_date = timezone.now().date().isoformat()
        for r in rows:
            r["teacher"] = "-"
            r["generatedDate"] = gen_date
        return rows


class AttendanceShortageExport(AggregationExportDefinition):
    report_type = ReportType.ATTENDANCE_SHORTAGE
    title = "Attendance Shortage"
    module = "attendance"
    description = "Students below the attendance threshold"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    supports_preview = True
    estimated_runtime = "instant"
    sync_threshold = 500
    filters = [
        ACADEMIC_YEAR_FILTER,
        FilterSpec("threshold", "Threshold %", type="number", group="criteria"),
        BATCH_FILTER,
        FilterSpec("fromDate", "From Date", type="date", group="criteria"),
        FilterSpec("toDate", "To Date", type="date", group="criteria"),
    ]

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("admissionNo", "Admission No"),
            Column("name", "Student Name"),
            Column("class", "Class"),
            Column("section", "Section"),
            Column("academicYear", "Academic Year"),
            Column("sessions", "Working Days", format="number"),
            Column("present", "Present Days", format="number"),
            Column("absent", "Absent Days", format="number"),
            Column("percent", "Attendance %", format="number"),
            Column("status", "Status"),
            Column("teacher", "Class Teacher"),
            Column("branchName", "Branch"),
            Column("generatedDate", "Generated Date", format="date"),
        ]

    def resolve_rows(self, *, tenant, branch, params: dict) -> list[dict]:
        year_obj, include_inactive = _year_scope(params, branch)
        threshold = params.get("threshold")
        rows = att_report.shortage_report(
            branch,
            threshold=int(threshold) if threshold else None,
            batch_id=params.get("batchId"),
            date_from=_parse_date(params.get("fromDate"), None),
            date_to=_parse_date(params.get("toDate"), None),
            academic_year_id=year_obj.pk,
            include_inactive=include_inactive,
        )["rows"]
        gen_date = timezone.now().date().isoformat()
        for r in rows:
            r["teacher"] = "-"
            r["generatedDate"] = gen_date
        return rows


class AttendanceRankingExport(AggregationExportDefinition):
    report_type = ReportType.ATTENDANCE_RANKING
    title = "Attendance Ranking"
    module = "attendance"
    description = "All students ranked by attendance %"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    supports_preview = True
    estimated_runtime = "instant"
    sync_threshold = 500
    filters = [
        ACADEMIC_YEAR_FILTER,
        BATCH_FILTER,
        FilterSpec("fromDate", "From Date", type="date", group="criteria"),
        FilterSpec("toDate", "To Date", type="date", group="criteria"),
    ]

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("rank", "Rank", format="number"),
            Column("admissionNo", "Admission No"),
            Column("name", "Student Name"),
            Column("class", "Class"),
            Column("section", "Section"),
            Column("percent", "Attendance %", format="number"),
            Column("present", "Present"),
            Column("absent", "Absent"),
            Column("sessions", "Working Days"),
        ]

    def resolve_rows(self, *, tenant, branch, params: dict) -> list[dict]:
        year_obj, include_inactive = _year_scope(params, branch)
        today = timezone.localdate()
        date_from = _parse_date(params.get("fromDate"), today.replace(day=1))
        date_to = _parse_date(params.get("toDate"), today)
        rows = att_report.ranking_report(
            branch,
            date_from=date_from,
            date_to=date_to,
            batch_id=params.get("batchId"),
            academic_year_id=year_obj.pk,
            include_inactive=include_inactive,
        )["rows"]
        rows.sort(key=lambda r: r["percent"], reverse=True)
        for i, r in enumerate(rows):
            r["rank"] = i + 1
        return rows


class AttendanceDetentionExport(AggregationExportDefinition):
    report_type = ReportType.ATTENDANCE_DETENTION
    title = "Attendance Detention"
    module = "attendance"
    description = "Students below threshold (detention list)"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    supports_preview = True
    estimated_runtime = "instant"
    sync_threshold = 500
    filters = [
        ACADEMIC_YEAR_FILTER,
        BATCH_FILTER,
        FilterSpec("fromDate", "From Date", type="date", group="criteria"),
        FilterSpec("toDate", "To Date", type="date", group="criteria"),
    ]

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("admissionNo", "Admission No"),
            Column("name", "Student Name"),
            Column("class", "Class"),
            Column("section", "Section"),
            Column("academicYear", "Academic Year"),
            Column("sessions", "Working Days", format="number"),
            Column("present", "Present Days", format="number"),
            Column("absent", "Absent Days", format="number"),
            Column("percent", "Attendance %", format="number"),
            Column("status", "Status"),
            Column("teacher", "Class Teacher"),
            Column("branchName", "Branch"),
            Column("generatedDate", "Generated Date", format="date"),
        ]

    def resolve_rows(self, *, tenant, branch, params: dict) -> list[dict]:
        year_obj, include_inactive = _year_scope(params, branch)
        rows = att_report.detention_report(
            branch,
            batch_id=params.get("batchId"),
            date_from=_parse_date(params.get("fromDate"), None),
            date_to=_parse_date(params.get("toDate"), None),
            academic_year_id=year_obj.pk,
            include_inactive=include_inactive,
        )["rows"]
        gen_date = timezone.now().date().isoformat()
        for r in rows:
            r["teacher"] = "-"
            r["generatedDate"] = gen_date
        return rows


def register_all() -> None:
    register(AdmissionFunnelExport())
    register(HrLeaveSummaryExport())
    register(AttendanceMonthlyExport())
    register(AttendanceShortageExport())
    register(AttendanceRankingExport())
    register(AttendanceDetentionExport())


register_all()
