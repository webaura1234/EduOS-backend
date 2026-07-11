"""Analytics enums."""

from django.db import models


class ReportStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"
    TIMED_OUT = "timed_out", "Timed Out"


class ReportType(models.TextChoices):
    ATTENDANCE_MONTHLY = "attendance_monthly", "Attendance — Monthly"
    FEE_DEFAULTERS = "fee_defaulters", "Fees — Defaulters"
    FEE_COLLECTION = "fee_collection", "Fees — Collection"
    ADMISSION_FUNNEL = "admission_funnel", "Admissions — Funnel"
    HR_LEAVE_SUMMARY = "hr_leave_summary", "HR — Leave Summary"
    HR_HEADCOUNT = "hr_headcount", "HR — Headcount"
    NAAC = "naac", "NAAC / NIRF"
    # Extended types — unified export framework
    FEE_LEDGER = "fee_ledger", "Fees — Ledger"
    ATTENDANCE_SHORTAGE = "attendance_shortage", "Attendance — Shortage"
    ATTENDANCE_RANKING = "attendance_ranking", "Attendance — Ranking"
    ATTENDANCE_DETENTION = "attendance_detention", "Attendance — Detention"
    # Self-service exports — faculty/student own-data only
    FACULTY_SUBJECT_ATTENDANCE = "faculty_subject_attendance", "Faculty — My Subject Attendance"
    FACULTY_CLASS_RESULTS = "faculty_class_results", "Faculty — My Class Results"
    STUDENT_ATTENDANCE = "student_attendance", "Student — My Attendance"
    STUDENT_FEE_STATEMENT = "student_fee_statement", "Student — My Fee Statement"
    STUDENT_EXAM_RESULTS = "student_exam_results", "Student — My Exam Results"
    # Super-admin — tenant-wide cross-branch export
    BRANCH_SUMMARY = "branch_summary", "Branches — Summary"
    # Sync CSV reports (instant delivery, logged to ReportExport)
    EXAM_SEATING = "exam_seating", "Examinations — Seating Plan"
    EXAM_CLASS_RESULTS = "exam_class_results", "Examinations — Class Results"
    COLLEGE_NAAC = "college_naac", "College — NAAC Export"
    COLLEGE_NIRF = "college_nirf", "College — NIRF Export"
