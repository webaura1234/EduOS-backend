"""Admissions enums."""

from django.db import models


class EnquirySource(models.TextChoices):
    WALK_IN = "walk_in", "Walk In"
    SOCIAL = "social", "Social Media"
    REFERRAL = "referral", "Referral"
    ONLINE = "online", "Online"


class EnquiryStatus(models.TextChoices):
    NEW = "new", "New"
    CONTACTED = "contacted", "Contacted"
    CONVERTED = "converted", "Converted"
    LOST = "lost", "Lost"


class ApplicationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    UNDER_REVIEW = "under_review", "Under Review"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    WAITLISTED = "waitlisted", "Waitlisted"
    ENROLLED = "enrolled", "Enrolled"


class DocVerificationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    VERIFIED = "verified", "Verified"
    REJECTED = "rejected", "Rejected"


class EnrollmentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    TRANSFERRED = "transferred", "Transferred"
    GRADUATED = "graduated", "Graduated"
    WITHDRAWN = "withdrawn", "Withdrawn"
