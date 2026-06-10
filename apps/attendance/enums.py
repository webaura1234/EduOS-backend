"""Enumerations for the attendance app."""

from django.db import models


class SessionStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    IN_PROGRESS = "in_progress", "In progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", "Present"
    ABSENT = "absent", "Absent"
    LATE = "late", "Late"
    FLAGGED = "flagged", "Flagged (needs review)"   # geo-fence failure (EC-ATT-03)
    EXCUSED = "excused", "Excused"
    LEAVE = "leave", "On approved leave"


class LeaveApplicantRole(models.TextChoices):
    STUDENT = "student", "Student"
    STAFF = "staff", "Staff"


class LeaveStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class AuditType(models.TextChoices):
    RETROACTIVE_EDIT = "retroactive_edit", "Retroactive edit"     # F-107 / EC-ATT-04
    LATE_MARKING = "late_marking", "Late marking"                 # F-108 / EC-ATT-02
    GEO_FENCE_FAILURE = "geo_fence_failure", "Geo-fence failure"  # F-103 / EC-ATT-03
