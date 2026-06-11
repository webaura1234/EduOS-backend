"""Fee structure + per-student assignment (with snapshot for F-150/EC-FEE-06)."""

from django.db import models

from apps.core.models import BaseModel


class FeeStructure(BaseModel):
    """
    A fee template for a batch/course in an academic year.

    `components` is a JSON list:
      [{"kind": "tuition", "label": "Tuition", "amount_paise": 5000000,
        "due_date": "2024-07-10", "installment_no": 1}, ...]

    Editing bumps `version`; existing assignments keep their snapshot (EC-FEE-06).
    """

    branch = models.ForeignKey("organizations.Branch", on_delete=models.CASCADE, related_name="fee_structures")
    batch = models.ForeignKey("academics.Batch", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="fee_structures")
    academic_year = models.ForeignKey("academics.AcademicYear", on_delete=models.CASCADE,
                                      related_name="fee_structures")
    name = models.CharField(max_length=150)
    components = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "fees_fee_structure"
        verbose_name = "Fee Structure"
        verbose_name_plural = "Fee Structures"
        indexes = [models.Index(fields=["branch", "academic_year"])]

    def __str__(self):
        return f"{self.name} (v{self.version})"

    @property
    def total_paise(self) -> int:
        return sum(int(c.get("amount_paise", 0)) for c in (self.components or []))


class StudentFeeAssignment(BaseModel):
    """
    Links a student to a fee structure, freezing a snapshot of the components so
    later structure edits never change what this student owes (EC-FEE-06).

    Student identity (ENROLLMENT SEAM): keyed off accounts.StudentProfile because
    admissions/StudentEnrollment (Stage 5) is not built yet.
    """

    student = models.ForeignKey("accounts.StudentProfile", on_delete=models.CASCADE,
                                related_name="fee_assignments")
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.PROTECT, related_name="assignments")
    structure_snapshot = models.JSONField(default=dict, blank=True)
    discount_lines = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "fees_student_fee_assignment"
        verbose_name = "Student Fee Assignment"
        verbose_name_plural = "Student Fee Assignments"
        constraints = [
            models.UniqueConstraint(fields=["student", "fee_structure"],
                                    name="unique_assignment_per_student_structure"),
        ]

    def __str__(self):
        return f"{self.student_id} → {self.fee_structure_id}"
