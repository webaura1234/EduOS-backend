"""Django admin registration for admissions models."""

from django.contrib import admin

from apps.admissions.models.application import Application, ApplicationDocument, Enquiry, Waitlist
from apps.admissions.models.enrollment import StudentEnrollment


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ["applicant_name", "branch", "source", "status", "created_at"]
    list_filter = ["source", "status", "branch"]
    search_fields = ["applicant_name", "phone", "email"]


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ["enquiry", "course", "status", "created_at"]
    list_filter = ["status", "course", "branch"]


@admin.register(ApplicationDocument)
class ApplicationDocumentAdmin(admin.ModelAdmin):
    list_display = ["application", "doc_type", "verification_status"]
    list_filter = ["verification_status"]


@admin.register(Waitlist)
class WaitlistAdmin(admin.ModelAdmin):
    list_display = ["application", "course", "rank"]
    list_filter = ["course", "branch"]


@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(admin.ModelAdmin):
    list_display = ["student_profile", "branch", "batch", "academic_year", "status"]
    list_filter = ["status", "academic_year", "branch"]
