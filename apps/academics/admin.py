from django.contrib import admin

from apps.academics.models import (
    AcademicPeriod,
    AcademicRolloverRun,
    AcademicYear,
    Batch,
    BatchFaculty,
    BatchSubject,
    Course,
    Department,
    Holiday,
    PeriodSlot,
    Room,
    Subject,
    Timetable,
    TimetableEntry,
)


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "start_date", "end_date", "is_current", "is_frozen")
    list_filter = ("is_current", "is_frozen")


@admin.register(AcademicPeriod)
class AcademicPeriodAdmin(admin.ModelAdmin):
    list_display = ("name", "academic_year", "period_type", "sequence", "start_date", "end_date")


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "date", "holiday_type")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "code", "department_type")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "code", "duration_years")


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "academic_year", "capacity")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "course", "code", "subject_type", "credits")


@admin.register(BatchSubject)
class BatchSubjectAdmin(admin.ModelAdmin):
    list_display = ("batch", "subject", "academic_period", "is_required")


@admin.register(BatchFaculty)
class BatchFacultyAdmin(admin.ModelAdmin):
    list_display = ("batch_subject", "faculty", "role", "assigned_at", "ended_at")


@admin.register(PeriodSlot)
class PeriodSlotAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "sequence", "start_time", "end_time")


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "code", "capacity", "is_lab")


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ("batch", "academic_period", "is_published")


@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = ("timetable", "batch_subject", "day_of_week", "period_slot", "status")


@admin.register(AcademicRolloverRun)
class AcademicRolloverRunAdmin(admin.ModelAdmin):
    list_display = ("branch", "from_year", "to_year", "status", "executed_at", "undo_expires_at")
