"""HR query-layer tests — staff-attendance batching (no-N+1 rollup)."""

import pytest
from django.utils import timezone

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.hr.queries import staff_attendance as sa_q
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def branch():
    tenant = TenantFactory(institution_type="school")
    return BranchFactory(tenant=tenant)


def _faculty(branch, login_id):
    return UserFactory(role=Role.FACULTY, tenant=branch.tenant, branch=branch,
                       custom_login_id=login_id, must_change_password=False)


def test_month_percent_by_user_matches_per_user_summary(branch):
    """Batched query must equal the per-user month_attendance_summary it replaces."""
    today = timezone.localdate()
    user = _faculty(branch, "FAC-1")
    # 6 present, 2 absent, 2 leave → present / (present+absent+leave) = 6/10 = 60%.
    day = 1
    for status, count in (("present", 6), ("absent", 2), ("leave", 2)):
        for _ in range(count):
            sa_q.check_in(branch, user, on_date=today.replace(day=day), status=status)
            day += 1

    per_user = sa_q.month_attendance_summary(user.pk, branch, today.year, today.month)
    batched = sa_q.month_attendance_percent_by_user([user.pk], today.year, today.month)

    assert per_user["attendancePercent"] == 60
    assert batched[user.pk] == per_user["attendancePercent"]


def test_month_percent_by_user_handles_many_and_unmarked(branch):
    today = timezone.localdate()
    a = _faculty(branch, "FAC-A")
    b = _faculty(branch, "FAC-B")
    unmarked = _faculty(branch, "FAC-C")

    sa_q.check_in(branch, a, on_date=today.replace(day=1), status="present")
    sa_q.check_in(branch, a, on_date=today.replace(day=2), status="absent")  # 50%
    sa_q.check_in(branch, b, on_date=today.replace(day=1), status="present")  # 100%

    result = sa_q.month_attendance_percent_by_user([a.pk, b.pk, unmarked.pk], today.year, today.month)
    assert result[a.pk] == 50
    assert result[b.pk] == 100
    assert result[unmarked.pk] == 0  # no records → 0, not a KeyError


def test_month_percent_by_user_empty_input():
    assert sa_q.month_attendance_percent_by_user([], 2026, 7) == {}
