"""Queries — account provisioning + duplicate detection for admissions.

All ORM that touches accounts (User / StudentProfile / StudentGuardianLink) for the
enrollment provisioning saga lives here, keeping the architecture's queries-only rule.
"""

import uuid

from django.db.models import Q

from apps.accounts.models.guardian import StudentGuardianLink
from apps.accounts.models.profile import AcademicStatus, GuardianProfile, StudentProfile
from apps.accounts.models.user import Role, User


def find_user_by_phone_or_email(tenant_id, *, phone=None, email=None, role=None) -> User | None:
    """Find an existing same-tenant user matching phone or email (parent linking / dup)."""
    q = Q()
    if phone:
        q |= Q(phone=phone)
    if email:
        q |= Q(email=email)
    if not q:
        return None
    qs = User.objects.filter(q, tenant_id=tenant_id, is_active=True)
    if role:
        qs = qs.filter(role=role)
    return qs.first()


def custom_login_id_taken(tenant_id, custom_login_id) -> bool:
    return User.objects.filter(
        tenant_id=tenant_id, custom_login_id=custom_login_id, is_active=True
    ).exists()


def find_duplicate_students(branch_id, *, name, date_of_birth, phone):
    """Possible-duplicate students by name + DOB + phone (F-080 / EC-DATA-03)."""
    name = (name or "").strip().lower()
    qs = StudentProfile.objects.select_related("user").filter(
        user__branch_id=branch_id, is_active=True
    )
    if date_of_birth:
        qs = qs.filter(date_of_birth=date_of_birth)
    matches = []
    for sp in qs:
        full = f"{sp.user.first_name} {sp.user.last_name}".strip().lower()
        phone_match = phone and (sp.user.phone == phone or sp.guardian_phone == phone)
        if full == name and phone_match:
            matches.append(sp)
    return matches


def create_student_user(*, tenant, branch, first_name, last_name, custom_login_id,
                        phone=None, email=None, user=None) -> User:
    return User.objects.create(
        tenant=tenant, branch=branch, role=Role.STUDENT,
        first_name=first_name, last_name=last_name,
        custom_login_id=custom_login_id, phone=phone, email=email or None,
        must_change_password=True,
    )


def create_student_profile(*, student_user, batch, date_of_birth=None, gender="",
                           guardian_phone=None, user=None) -> StudentProfile:
    return StudentProfile.objects.create(
        user=student_user, current_batch=batch, academic_status=AcademicStatus.ACTIVE,
        date_of_birth=date_of_birth, gender=gender, guardian_phone=guardian_phone,
        admission_date=None, created_by=user, updated_by=user,
    )


def create_parent_user(*, tenant, branch, first_name, last_name, phone=None, email=None,
                       linked_user_group_id=None) -> User:
    return User.objects.create(
        tenant=tenant, branch=branch, role=Role.PARENT,
        first_name=first_name, last_name=last_name,
        phone=phone, email=email or None,
        linked_user_group_id=linked_user_group_id,
        must_change_password=True,
    )


def get_guardian_profile(parent_user) -> GuardianProfile:
    profile, _ = GuardianProfile.objects.get_or_create(user=parent_user)
    return profile


def create_guardian_link(*, student_user, guardian_user, relationship="guardian",
                         is_primary_contact=True, has_portal_access=True) -> StudentGuardianLink:
    return StudentGuardianLink.objects.create(
        student=student_user, guardian=guardian_user, relationship=relationship,
        is_primary_contact=is_primary_contact, has_portal_access=has_portal_access,
    )


def active_student_count(tenant_id) -> int:
    return StudentProfile.objects.filter(
        user__tenant_id=tenant_id, academic_status=AcademicStatus.ACTIVE, is_active=True
    ).count()


def student_hard_cap(tenant_id):
    """The hard cap on active students for a tenant, or None if uncapped."""
    from apps.organizations.models import TenantQuota
    quota = TenantQuota.objects.filter(
        tenant_id=tenant_id, resource="student", hard_cap__gt=0, is_active=True
    ).order_by("-period_start").first()
    return quota.hard_cap if quota else None


def link_user_group(*users) -> uuid.UUID:
    """Assign a shared linked_user_group_id to a set of User rows (multi-role person)."""
    group_id = uuid.uuid4()
    for u in users:
        if u and not u.linked_user_group_id:
            u.linked_user_group_id = group_id
            u.save(update_fields=["linked_user_group_id"])
    return group_id
