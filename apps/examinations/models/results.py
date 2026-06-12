"""Examinations — registration, logistics, marks, and results."""

from django.db import models

from apps.core.models import BaseModel
from apps.examinations.enums import MarksStatus


class ExamRegistration(BaseModel):
    """
    Student registration for an exam (F-118/F-127/F-152).

    # ENROLLMENT SEAM — student FK migrates to StudentEnrollment in Stage 5.
    """

    exam = models.ForeignKey(
        "examinations.Exam",
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    student = models.ForeignKey(
        "admissions.StudentEnrollment",
        on_delete=models.CASCADE,
        related_name="exam_registrations",
    )
    fee_invoice = models.ForeignKey(
        "fees.FeeInvoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_registrations",
    )
    fee_paid = models.BooleanField(
        default=False,
        help_text="Derived from fee_invoice.status == PAID; cached for hall-ticket gate.",
    )
    is_arrear = models.BooleanField(
        default=False,
        help_text="College arrear registration (F-049/F-129).",
    )

    class Meta:
        db_table = "examinations_exam_registration"
        verbose_name = "Exam Registration"
        verbose_name_plural = "Exam Registrations"
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student"],
                name="unique_registration_per_exam_student",
            ),
        ]

    def __str__(self):
        return f"{self.exam_id} — {self.student_id}"


class HallTicket(BaseModel):
    """
    Generated admit card for a registered student (F-117/F-047).

    Generation blocked when fee_paid is false (EC-EXAM-01).
    """

    registration = models.OneToOneField(
        ExamRegistration,
        on_delete=models.CASCADE,
        related_name="hall_ticket",
    )
    file_key = models.CharField(max_length=512, blank=True, default="")
    roll_number = models.CharField(max_length=50, blank=True, default="")
    regulation = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="College regulation code; blank for school.",
    )
    generated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "examinations_hall_ticket"
        verbose_name = "Hall Ticket"
        verbose_name_plural = "Hall Tickets"

    def __str__(self):
        return f"Hall ticket — {self.registration_id}"


class Seating(BaseModel):
    """
    Room/seat allocation for a student in a schedule slot (F-118/EC-EXAM-05).

    # ENROLLMENT SEAM — student FK migrates to StudentEnrollment in Stage 5.
    """

    schedule_slot = models.ForeignKey(
        "examinations.ExamScheduleSlot",
        on_delete=models.CASCADE,
        related_name="seatings",
    )
    student = models.ForeignKey(
        "admissions.StudentEnrollment",
        on_delete=models.CASCADE,
        related_name="exam_seatings",
    )
    room = models.ForeignKey(
        "academics.Room",
        on_delete=models.PROTECT,
        related_name="exam_seatings",
    )
    seat_number = models.CharField(max_length=20)

    class Meta:
        db_table = "examinations_seating"
        verbose_name = "Seating"
        verbose_name_plural = "Seatings"
        constraints = [
            models.UniqueConstraint(
                fields=["schedule_slot", "room", "seat_number"],
                name="unique_seat_per_slot_room",
            ),
            models.UniqueConstraint(
                fields=["schedule_slot", "student"],
                name="unique_student_per_schedule_slot",
            ),
        ]

    def __str__(self):
        return f"{self.schedule_slot_id} — seat {self.seat_number}"


class MarksEntry(BaseModel):
    """
    Faculty-entered marks for a student in a subject exam (F-120/F-121/F-188).

    marks=null means absent (EC-EXAM-04). Optimistic concurrency via BaseModel.version.

    # ENROLLMENT SEAM — student FK migrates to StudentEnrollment in Stage 5.
    """

    exam = models.ForeignKey(
        "examinations.Exam",
        on_delete=models.CASCADE,
        related_name="marks_entries",
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.PROTECT,
        related_name="marks_entries",
    )
    student = models.ForeignKey(
        "admissions.StudentEnrollment",
        on_delete=models.CASCADE,
        related_name="marks_entries",
    )
    marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Null = absent (EC-EXAM-04).",
    )
    is_absent = models.BooleanField(default=False)
    is_internal = models.BooleanField(
        default=False,
        help_text="Internal/continuous assessment marks vs exam marks.",
    )
    marks_status = models.CharField(
        max_length=15,
        choices=MarksStatus.choices,
        default=MarksStatus.DRAFT,
    )
    grace_applied = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="College-only grace marks applied (F-050).",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "examinations_marks_entry"
        verbose_name = "Marks Entry"
        verbose_name_plural = "Marks Entries"
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "subject", "student"],
                name="unique_marks_per_exam_subject_student",
            ),
        ]
        indexes = [
            models.Index(fields=["exam", "subject", "marks_status"]),
        ]

    def __str__(self):
        return f"{self.exam_id} — {self.subject_id} — {self.student_id}"


class ResultPublication(BaseModel):
    """
    Two-step publish record for exam results (F-122/EC-EXAM-02).

    snapshot_hash is sha256 of the frozen marks set at publish time.
    """

    exam = models.ForeignKey(
        "examinations.Exam",
        on_delete=models.CASCADE,
        related_name="publications",
    )
    published_at = models.DateTimeField()
    published_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_result_publications",
    )
    snapshot_hash = models.CharField(max_length=64)
    is_revised = models.BooleanField(default=False)
    revision_no = models.PositiveSmallIntegerField(default=0)
    parent_publication = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revisions",
    )
    is_current = models.BooleanField(
        default=True,
        help_text="False once superseded by a revision (EC-CONCUR-01 partial unique).",
    )

    class Meta:
        db_table = "examinations_result_publication"
        verbose_name = "Result Publication"
        verbose_name_plural = "Result Publications"
        constraints = [
            models.UniqueConstraint(
                fields=["exam"],
                condition=models.Q(is_current=True),
                name="unique_current_publication_per_exam",
            ),
        ]

    def __str__(self):
        return f"{self.exam_id} — rev {self.revision_no}"


class ResultRevisionHistory(BaseModel):
    """
    Immutable append-only log of post-publish result changes (F-123/EC-EXAM-03).

    Published results are revised, never deleted.
    """

    publication = models.ForeignKey(
        ResultPublication,
        on_delete=models.CASCADE,
        related_name="revision_history",
    )
    changed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exam_result_revisions",
    )
    change_summary = models.TextField(blank=True, default="")
    field_changes = models.JSONField(
        default=dict,
        help_text="Structured diff of changed fields.",
    )
    previous_snapshot_hash = models.CharField(max_length=64, blank=True, default="")
    new_snapshot_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "examinations_result_revision_history"
        verbose_name = "Result Revision History"
        verbose_name_plural = "Result Revision Histories"
        ordering = ["created_at"]

    def __str__(self):
        return f"Revision for {self.publication_id} @ {self.created_at}"


class StudentResult(BaseModel):
    """
    Computed final result per student per exam (F-131/F-132/F-202).

    School: report_card_key. College: marksheet_key + GPA + arrears.

    # ENROLLMENT SEAM — student FK migrates to StudentEnrollment in Stage 5.
    """

    exam = models.ForeignKey(
        "examinations.Exam",
        on_delete=models.CASCADE,
        related_name="student_results",
    )
    student = models.ForeignKey(
        "admissions.StudentEnrollment",
        on_delete=models.CASCADE,
        related_name="exam_results",
    )
    publication = models.ForeignKey(
        ResultPublication,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_results",
    )
    total_marks = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    grade = models.CharField(max_length=10, blank=True, default="")
    gpa = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="College SGPA; null for school.",
    )
    is_pass = models.BooleanField(default=False)
    arrear_subjects = models.JSONField(
        default=list,
        help_text="College arrear subject ids/names (F-049).",
    )
    report_card_key = models.CharField(max_length=512, blank=True, default="")
    marksheet_key = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        db_table = "examinations_student_result"
        verbose_name = "Student Result"
        verbose_name_plural = "Student Results"
        constraints = [
            models.UniqueConstraint(
                fields=["exam", "student"],
                name="unique_result_per_exam_student",
            ),
        ]

    def __str__(self):
        return f"{self.exam_id} — {self.student_id} — {self.grade}"
