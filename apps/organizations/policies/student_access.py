"""Student access policy — what an unlicensed student (or a student in an
expired tenant) can and cannot use.

Design decisions (balance customer experience vs revenue protection):
  - NEVER blocked, regardless of license: admissions, admin/faculty ERP,
    attendance marking (faculty marks it), institution fee collection, exams
    conducted by the school. These are the school's operations, not the
    student's premium features.
  - Unlicensed student: the student's own portal access is restricted —
    login/mobile app content, report cards, certificates, library, transport,
    hostel, gallery, and AI features are blocked. The fees module stays open
    so families can still pay the school.
  - Subscription grace: warning only, nothing extra blocked.
  - Subscription expired: all students lose premium modules (the school keeps
    admin/faculty access and billing so it can renew).
"""

from __future__ import annotations

from apps.organizations.enums import StudentLicenseStatus, SubscriptionPeriodStatus
from apps.organizations.models import StudentLicense
from apps.organizations.queries.licensing import active_period_status

# Modules blocked for an UNLICENSED student. Ids match the student portal nav
# (STUDENT_NAV in the frontend) so shells can filter directly.
UNLICENSED_BLOCKED_MODULES = [
    "learn",          # study materials / assignments
    "timetable",
    "homework",
    "classroomQuiz",
    "exams",          # results / report cards / certificates
    "gallery",
    "view360",
    "transport",
    "library",
    "assistant",      # AI features
    "referral",
]

# Modules every student keeps even when unlicensed: dashboard (with paywall
# notice), fees (families must still be able to pay the school), notices,
# alerts, leave, help, and account.
ALWAYS_ALLOWED_MODULES = ["dashboard", "fees", "leave", "alerts", "notices", "help", "account"]

# When the tenant subscription is fully expired, students lose premium modules.
EXPIRED_BLOCKED_MODULES = UNLICENSED_BLOCKED_MODULES


def get_student_access(student_user) -> dict:
    """Access decision for one student user.

    Returns { licenseStatus, subscriptionStatus, blockedModules }.
    blockedModules empty ⇒ full access.
    """
    license_row = StudentLicense.objects.filter(student_user=student_user).first()
    license_status = license_row.license_status if license_row else None
    subscription_status = (
        active_period_status(student_user.tenant_id) if student_user.tenant_id else None
    )

    blocked: list[str] = []
    if subscription_status == SubscriptionPeriodStatus.EXPIRED:
        blocked = list(EXPIRED_BLOCKED_MODULES)
    elif license_status == StudentLicenseStatus.UNLICENSED:
        blocked = list(UNLICENSED_BLOCKED_MODULES)

    return {
        "licenseStatus": license_status,
        "subscriptionStatus": subscription_status,
        "blockedModules": blocked,
    }
