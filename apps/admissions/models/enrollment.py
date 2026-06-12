"""
Admissions — the enrollment anchor record.

  - StudentEnrollment → the canonical per-(student, academic_year) record that
    Attendance, Fees, and Examinations key off (the enrollment seam, Stage 5 / OD-1 A).

To keep the downstream modules' attribute access stable after the FK migration,
StudentEnrollment exposes convenience properties that mirror the StudentProfile API it
replaced: `.current_batch`, `.current_batch_id`, `.user`, `.academic_status`.
"""

import uuid

from django.db import models

from apps.admissions.enums import EnrollmentStatus
from apps.core.models import BaseModel


class StudentEnrollment(BaseModel):
    """One active enrollment per student per academic year (F-081)."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="enrollments"
    )
    student_profile = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="enrollments"
    )
    batch = models.ForeignKey(
        "academics.Batch", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="enrollments", db_index=True,
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear", on_delete=models.CASCADE, related_name="enrollments"
    )
    application = models.ForeignKey(
        "admissions.Application", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="enrollments",
    )
    fee_structure_snapshot = models.ForeignKey(
        "fees.FeeStructure", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="snapshot_enrollments",
    )
    status = models.CharField(
        max_length=15, choices=EnrollmentStatus.choices,
        default=EnrollmentStatus.ACTIVE, db_index=True,
    )

    # Transfer lineage (F-085 / EC-XFER).
    is_transferred = models.BooleanField(default=False)
    transferred_from_branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="transferred_enrollments",
    )

    # College arrear carry-forward (EC-ROL-05).
    backlog_subjects = models.JSONField(default=list, blank=True)

    # Twin / sibling disambiguation on duplicate override (EC-GUARD-06).
    sibling_group_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "admissions_student_enrollment"
        constraints = [
            models.UniqueConstraint(
                fields=["student_profile", "academic_year"],
                name="unique_enrollment_per_student_year",
            )
        ]
        indexes = [
            models.Index(fields=["batch", "academic_year"]),
            models.Index(fields=["student_profile", "is_active"]),
        ]

    def __str__(self):
        return f"Enrollment({self.student_profile_id}, {self.academic_year_id})"

    # ── Convenience mirrors of the StudentProfile API (enrollment-seam shim) ──
    @property
    def current_batch(self):
        return self.batch

    @property
    def current_batch_id(self):
        return self.batch_id

    @property
    def user(self):
        return self.student_profile.user

    @property
    def user_id(self):
        return self.student_profile.user_id

    @property
    def academic_status(self):
        return self.student_profile.academic_status
