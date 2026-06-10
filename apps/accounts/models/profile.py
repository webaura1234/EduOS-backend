"""
Role-specific profile models.

Every User row has a corresponding profile row that holds role-specific
data. These are kept separate from the User model to keep the core
identity table lean and fast.

  - FacultyProfile  → for User.role == 'faculty'
  - StudentProfile  → for User.role == 'student'
  - GuardianProfile → for User.role == 'parent'
"""

import uuid

from django.db import models

from apps.core.models import BaseModel


class Gender(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"
    OTHER = "other", "Other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer Not to Say"


class EmploymentType(models.TextChoices):
    FULL_TIME = "full_time", "Full Time"
    PART_TIME = "part_time", "Part Time"
    CONTRACT = "contract", "Contract"
    VISITING = "visiting", "Visiting"


class AcademicStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    GRADUATED = "graduated", "Graduated"
    TRANSFERRED = "transferred", "Transferred"
    WITHDRAWN = "withdrawn", "Withdrawn"


class RelationshipType(models.TextChoices):
    FATHER = "father", "Father"
    MOTHER = "mother", "Mother"
    GUARDIAN = "guardian", "Guardian"
    GRANDPARENT = "grandparent", "Grandparent"
    SIBLING = "sibling", "Sibling"
    OTHER = "other", "Other"


class FacultyProfile(BaseModel):
    """
    Extended profile for Faculty users.
    Linked 1-to-1 with a User row where role='faculty'.
    """

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="faculty_profile",
    )

    # Professional details
    designation = models.CharField(max_length=150, blank=True, default="")
    department = models.CharField(max_length=150, blank=True, default="")
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.FULL_TIME,
    )
    date_of_joining = models.DateField(null=True, blank=True)
    date_of_leaving = models.DateField(null=True, blank=True)

    # Personal details
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)
    blood_group = models.CharField(max_length=5, blank=True, default="")
    address = models.TextField(blank=True, default="")
    emergency_contact_name = models.CharField(max_length=150, blank=True, default="")
    emergency_contact_phone = models.CharField(max_length=20, blank=True, default="")

    # Qualifications
    highest_qualification = models.CharField(max_length=150, blank=True, default="")
    specialization = models.CharField(max_length=150, blank=True, default="")
    experience_years = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "accounts_faculty_profile"
        verbose_name = "Faculty Profile"
        verbose_name_plural = "Faculty Profiles"

    def __str__(self):
        return f"FacultyProfile({self.user.full_name})"


class StudentProfile(BaseModel):
    """
    Extended profile for Student users.
    Linked 1-to-1 with a User row where role='student'.
    """

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="student_profile",
    )

    # Personal details
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)
    blood_group = models.CharField(max_length=5, blank=True, default="")
    address = models.TextField(blank=True, default="")
    nationality = models.CharField(max_length=100, blank=True, default="")
    religion = models.CharField(max_length=100, blank=True, default="")

    # Academic placement — school section / college batch (academics.Batch)
    current_batch = models.ForeignKey(
        "academics.Batch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_students",
        db_index=True,
        help_text="Current section (school) or batch (college) for this student.",
    )
    admission_date = models.DateField(null=True, blank=True)
    academic_status = models.CharField(
        max_length=15,
        choices=AcademicStatus.choices,
        default=AcademicStatus.ACTIVE,
        db_index=True,
    )

    # Used for password reset when student has no phone
    # Populated from the primary guardian's phone
    guardian_phone = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        db_table = "accounts_student_profile"
        verbose_name = "Student Profile"
        verbose_name_plural = "Student Profiles"

    def __str__(self):
        return f"StudentProfile({self.user.full_name})"


class GuardianProfile(BaseModel):
    """
    Extended profile for Parent/Guardian users.
    Linked 1-to-1 with a User row where role='parent'.
    """

    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="guardian_profile",
    )

    # Default relationship type (can be overridden per StudentGuardianLink)
    relationship_default = models.CharField(
        max_length=20,
        choices=RelationshipType.choices,
        default=RelationshipType.GUARDIAN,
    )
    occupation = models.CharField(max_length=150, blank=True, default="")
    annual_income_range = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        db_table = "accounts_guardian_profile"
        verbose_name = "Guardian Profile"
        verbose_name_plural = "Guardian Profiles"

    def __str__(self):
        return f"GuardianProfile({self.user.full_name})"
