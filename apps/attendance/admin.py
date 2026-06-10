"""Django admin for attendance."""

from django.contrib import admin

from apps.attendance.models import (
    AttendanceAudit,
    AttendanceRecord,
    AttendanceSession,
    LeaveRequest,
)


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "batch_subject", "date", "period_slot", "status", "faculty")
    list_filter = ("status", "is_exam_day")
    raw_id_fields = ("branch", "batch_subject", "period_slot", "faculty")


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "student", "status", "late_mark", "marked_at")
    list_filter = ("status", "late_mark")
    raw_id_fields = ("session", "student", "marked_by")


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "applicant_role", "student", "employee", "from_date", "to_date", "status")
    list_filter = ("applicant_role", "status")
    raw_id_fields = ("branch", "student", "employee", "applied_by", "approver")


@admin.register(AttendanceAudit)
class AttendanceAuditAdmin(admin.ModelAdmin):
    list_display = ("id", "record", "audit_type", "original_status", "new_status", "actor", "created_at")
    list_filter = ("audit_type",)
    raw_id_fields = ("record", "actor")
