"""Aggregation-style report definitions — registered on analytics app startup."""

import datetime

from django.utils import timezone

from apps.accounts.models.user import Role
from apps.admissions.queries.enquiry import funnel_counts
from apps.analytics.enums import ReportType
from apps.attendance.interactors import report as att_report
from apps.core.exports.base import AggregationExportDefinition, Column, FilterSpec
from apps.core.exports.registry import register
from apps.hr.queries.leave import leave_summary


def _parse_date(value, default):
    if not value:
        return default
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


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

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("stage", "Stage"),
            Column("students", "Students", format="number"),
            Column("conversion", "Conversion %", format="number"),
            Column("dropoffs", "Drop-offs", format="number"),
        ]

    def resolve_rows(self, *, tenant, branch, params: dict) -> list[dict]:
        from apps.admissions.enums import EnquiryStatus
        f = funnel_counts(branch.pk)
        by_status = f.get("byStatus", {})
        
        # Define typical funnel stages in order
        stages = [
            (EnquiryStatus.NEW, "New Enquiries"),
            (EnquiryStatus.CONTACTED, "Contacted"),
            (EnquiryStatus.TOUR_SCHEDULED, "Tour Scheduled"),
            (EnquiryStatus.APPLICATION_STARTED, "Application Started"),
            (EnquiryStatus.APPLICATION_SUBMITTED, "Application Submitted"),
            (EnquiryStatus.ADMITTED, "Admitted"),
            (EnquiryStatus.ENROLLED, "Enrolled"),
        ]
        
        rows = []
        prev_count = 0
        
        for enum_val, label in stages:
            count = by_status.get(enum_val, 0)
            
            # Since some stages might be skipped, we calculate conversion 
            # against the maximum of all previous stages, or just keep it simple:
            # Drop-offs is difference from previous stage (if prev > count).
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
            # Update prev_count to max seen so far to prevent negative dropoffs if a stage is skipped
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
        
        employees = (
            Employee.objects.filter(branch=branch, is_active=True)
            .select_related("user")
            .prefetch_related("leave_balances", "leave_applications")
        )
        
        rows = []
        for emp in employees:
            used_by_type = {}
            for app in emp.leave_applications.all():
                if app.status == LeaveStatus.APPROVED and app.is_active:
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
        FilterSpec("year", "Year", type="number", required=True),
        FilterSpec("month", "Month", type="number", required=True),
        FilterSpec("batchId", "Batch", type="batch_id"),
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
        year = int(params.get("year", timezone.now().year))
        month = int(params.get("month", timezone.now().month))
        rows = att_report.monthly_report(
            branch, year=year, month=month, batch_id=params.get("batchId"),
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
        FilterSpec("threshold", "Threshold %", type="number"),
        FilterSpec("batchId", "Batch", type="batch_id"),
        FilterSpec("fromDate", "From Date", type="date"),
        FilterSpec("toDate", "To Date", type="date"),
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
        threshold = params.get("threshold")
        rows = att_report.shortage_report(
            branch,
            threshold=int(threshold) if threshold else None,
            batch_id=params.get("batchId"),
            date_from=_parse_date(params.get("fromDate"), None),
            date_to=_parse_date(params.get("toDate"), None),
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
        FilterSpec("batchId", "Batch", type="batch_id"),
        FilterSpec("fromDate", "From Date", type="date"),
        FilterSpec("toDate", "To Date", type="date"),
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
        today = timezone.localdate()
        date_from = _parse_date(params.get("fromDate"), today.replace(day=1))
        date_to = _parse_date(params.get("toDate"), today)
        rows = att_report.ranking_report(
            branch, date_from=date_from, date_to=date_to, batch_id=params.get("batchId"),
        )["rows"]
        # Ranking rows are already sorted by percent ascending by default, wait we want descending?
        # Actually ranking is highest attendance first usually, let's sort descending
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
        FilterSpec("batchId", "Batch", type="batch_id"),
        FilterSpec("fromDate", "From Date", type="date"),
        FilterSpec("toDate", "To Date", type="date"),
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
        rows = att_report.detention_report(
            branch,
            batch_id=params.get("batchId"),
            date_from=_parse_date(params.get("fromDate"), None),
            date_to=_parse_date(params.get("toDate"), None),
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
