"""
User model for EduOS.

Roles and login identifiers (product-level rule, not configurable):
  - super_admin  → login via phone
  - admin        → login via phone
  - parent       → login via phone
  - faculty      → login via custom_login_id (Employee ID)
  - student      → login via custom_login_id (Roll Number / Admission No.)

A single real person can hold two roles (e.g. Admin + Parent).
These are stored as TWO separate User rows linked by linked_user_group_id.
"""

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    SUPER_ADMIN = "super_admin", "Super Admin"
    ADMIN = "admin", "Admin"
    FACULTY = "faculty", "Faculty"
    STUDENT = "student", "Student"
    PARENT = "parent", "Parent"


# Roles that log in with phone
PHONE_LOGIN_ROLES = {Role.SUPER_ADMIN, Role.ADMIN, Role.PARENT}

# Roles that log in with custom_login_id
CUSTOM_ID_LOGIN_ROLES = {Role.FACULTY, Role.STUDENT}


class CustomUserManager(BaseUserManager):
    """Manager for email-less, role-based User model."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", Role.SUPER_ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Core identity record for every EduOS user.

    A real person holding two roles (e.g. Admin + Parent) is represented as
    TWO rows in this table, linked via linked_user_group_id.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Personal identity ────────────────────────────────────────────
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True, default="")
    email = models.EmailField(blank=True, null=True, unique=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    # ── Login identifiers ────────────────────────────────────────────
    # Phone: used by super_admin, admin, parent to log in + ALL roles for OTP reset
    phone = models.CharField(max_length=20, blank=True, null=True, db_index=True)

    # custom_login_id: used by faculty (Employee ID) and student (Roll Number)
    custom_login_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)

    # ── Role ─────────────────────────────────────────────────────────
    role = models.CharField(max_length=20, choices=Role.choices, db_index=True)

    # ── Multi-role linking ───────────────────────────────────────────
    # A UUID shared by all User rows that represent the same real person.
    # e.g. Admin Sharma and Parent Sharma share the same linked_user_group_id.
    linked_user_group_id = models.UUIDField(blank=True, null=True, db_index=True)

    # ── Tenant / Branch scoping ──────────────────────────────────────
    # tenant is always set; branch is optional (super_admin manages all branches)
    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users",
        db_index=True,
    )
    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users",
        db_index=True,
    )

    # ── Django auth flags ────────────────────────────────────────────
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    date_joined = models.DateTimeField(default=timezone.now)

    # ── First-login enforcement ──────────────────────────────────────
    must_change_password = models.BooleanField(default=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "accounts_user"
        verbose_name = "User"
        verbose_name_plural = "Users"
        # A custom_login_id must be unique within a tenant
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "custom_login_id"],
                condition=models.Q(custom_login_id__isnull=False),
                name="unique_custom_login_id_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.role})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def login_identifier(self):
        """Returns the identifier this user uses to log in."""
        if self.role in CUSTOM_ID_LOGIN_ROLES:
            return self.custom_login_id
        return self.phone
