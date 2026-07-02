"""Query-layer tests — batched per-branch head-counts used by the super-admin dashboard.

These lock the grouped queries that replaced per-branch `.count()` round-trips in
`apps/analytics/interactors/dashboard.py`: each grouped result must equal the sum of the
old per-branch counts, and must key each count to the correct branch.
"""

import pytest

from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.queries.user import (
    count_active_by_role_grouped_by_branch,
    count_active_by_role_in_branch,
)
from apps.accounts.tests.factories import UserFactory
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.attendance.queries.roster import (
    active_student_counts_by_branch,
    all_active_students_in_branch,
)
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _enroll_students(tenant, branch, n, prefix):
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    for i in range(n):
        user = UserFactory(
            role=Role.STUDENT,
            tenant=tenant,
            branch=branch,
            custom_login_id=f"{prefix}-{i}",
            must_change_password=False,
        )
        profile = StudentProfile.objects.create(user=user, current_batch=batch)
        StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)


def test_active_student_counts_by_branch_matches_per_branch():
    tenant = TenantFactory(institution_type="school")
    branch_a = BranchFactory(tenant=tenant)
    branch_b = BranchFactory(tenant=tenant)
    branch_empty = BranchFactory(tenant=tenant)

    _enroll_students(tenant, branch_a, 2, "STU-A")
    _enroll_students(tenant, branch_b, 3, "STU-B")

    grouped = active_student_counts_by_branch([branch_a.pk, branch_b.pk, branch_empty.pk])

    # Keyed to the right branch, equal to the old per-branch .count().
    assert grouped.get(branch_a.pk, 0) == all_active_students_in_branch(branch_a.pk).count() == 2
    assert grouped.get(branch_b.pk, 0) == all_active_students_in_branch(branch_b.pk).count() == 3
    # A branch with no enrollments is simply absent (dashboard uses .get(pk, 0)).
    assert branch_empty.pk not in grouped


def test_faculty_counts_grouped_by_branch_matches_per_branch():
    tenant = TenantFactory(institution_type="school")
    branch_a = BranchFactory(tenant=tenant)
    branch_b = BranchFactory(tenant=tenant)

    for _ in range(1):
        UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch_a, must_change_password=False)
    for _ in range(2):
        UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch_b, must_change_password=False)

    grouped = count_active_by_role_grouped_by_branch(tenant.pk, Role.FACULTY)

    assert grouped.get(branch_a.pk, 0) == count_active_by_role_in_branch(branch_a.pk, Role.FACULTY) == 1
    assert grouped.get(branch_b.pk, 0) == count_active_by_role_in_branch(branch_b.pk, Role.FACULTY) == 2
