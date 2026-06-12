"""Django admin for examinations."""

from django.contrib import admin

from apps.examinations.models import (
    Assignment,
    AssignmentSubmission,
    Exam,
    ExamRegistration,
    ExamScheduleSlot,
    GradeScale,
    HallTicket,
    InvigilatorDuty,
    MarksEntry,
    ResultPublication,
    ResultRevisionHistory,
    Seating,
    StudentResult,
)


@admin.register(GradeScale)
class GradeScaleAdmin(admin.ModelAdmin):
    list_display = ("id", "branch", "course", "name", "is_default", "grace_marks_max")
    list_filter = ("is_default",)
    raw_id_fields = ("branch", "course")


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ("id", "branch", "name", "exam_type", "result_status", "is_published")
    list_filter = ("exam_type", "result_status", "is_published")
    raw_id_fields = ("branch", "academic_period")


@admin.register(ExamScheduleSlot)
class ExamScheduleSlotAdmin(admin.ModelAdmin):
    list_display = ("id", "exam", "subject", "batch", "room", "start_at", "end_at")
    raw_id_fields = ("exam", "subject", "batch", "room")


@admin.register(InvigilatorDuty)
class InvigilatorDutyAdmin(admin.ModelAdmin):
    list_display = ("id", "schedule_slot", "faculty")
    raw_id_fields = ("schedule_slot", "faculty")


@admin.register(ExamRegistration)
class ExamRegistrationAdmin(admin.ModelAdmin):
    list_display = ("id", "exam", "student", "fee_paid", "is_arrear")
    list_filter = ("fee_paid", "is_arrear")
    raw_id_fields = ("exam", "student", "fee_invoice")


@admin.register(HallTicket)
class HallTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "registration", "roll_number", "generated_at")
    raw_id_fields = ("registration",)


@admin.register(Seating)
class SeatingAdmin(admin.ModelAdmin):
    list_display = ("id", "schedule_slot", "student", "room", "seat_number")
    raw_id_fields = ("schedule_slot", "student", "room")


@admin.register(MarksEntry)
class MarksEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "exam", "subject", "student", "marks", "is_absent", "marks_status")
    list_filter = ("marks_status", "is_absent", "is_internal")
    raw_id_fields = ("exam", "subject", "student")


@admin.register(ResultPublication)
class ResultPublicationAdmin(admin.ModelAdmin):
    list_display = ("id", "exam", "revision_no", "is_revised", "is_current", "published_at")
    list_filter = ("is_revised", "is_current")
    raw_id_fields = ("exam", "published_by", "parent_publication")


@admin.register(ResultRevisionHistory)
class ResultRevisionHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "publication", "changed_by", "created_at")
    raw_id_fields = ("publication", "changed_by")


@admin.register(StudentResult)
class StudentResultAdmin(admin.ModelAdmin):
    list_display = ("id", "exam", "student", "grade", "percentage", "is_pass", "gpa")
    list_filter = ("is_pass",)
    raw_id_fields = ("exam", "student", "publication")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "branch", "batch_subject", "title", "due_at", "status")
    list_filter = ("status",)
    raw_id_fields = ("branch", "batch_subject", "created_by")


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "assignment", "student", "submission_status", "graded_marks")
    list_filter = ("submission_status",)
    raw_id_fields = ("assignment", "student")
