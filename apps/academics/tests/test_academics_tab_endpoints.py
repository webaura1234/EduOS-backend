"""Tests for tab-scoped admin academics endpoints and day-of-week normalization."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.academics.helpers import entry_matches_date, js_day_to_iso
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _body(resp):
    payload = resp.json()
    return payload.get("data", payload)


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919810000099",
        custom_login_id=None,
        must_change_password=False,
    )
    return dict(tenant=tenant, branch=branch, admin=admin)


@pytest.mark.parametrize(
    ("js_day", "iso_day"),
    [(0, 7), (1, 1), (6, 6)],
)
def test_js_day_to_iso(js_day, iso_day):
    assert js_day_to_iso(js_day) == iso_day


def test_entry_matches_date_uses_iso_weekday():
    monday = datetime.date(2026, 6, 22)
    assert entry_matches_date(1, monday) is True
    assert entry_matches_date(0, monday) is False


def test_admin_calendar_tab_endpoint(env):
    res = _client(env["admin"]).get(reverse("academics:admin-calendar-tab"))
    assert res.status_code == 200
    body = _body(res)
    assert "holidays" in body
    assert "workingDays" in body
    assert "timetableSlots" in body
    assert "subjectTeachers" in body


def test_admin_timetable_tab_includes_clashes(env):
    res = _client(env["admin"]).get(reverse("academics:admin-timetable-tab"))
    assert res.status_code == 200
    body = _body(res)
    assert "timetableSlots" in body
    assert "clashes" in body
    assert "adminReviewQueue" in body
    assert "subjectTeachers" in body
    assert isinstance(body["subjectTeachers"], list)


def test_resolve_review_dismisses_queue_item(env):
    client = _client(env["admin"])
    res = client.post(
        reverse("academics:admin-actions"),
        {"action": "resolve_review", "reviewId": "review-tbd"},
        format="json",
    )
    assert res.status_code == 200
    overview = _body(client.get(reverse("academics:admin-timetable-tab")))
    matching = [i for i in overview["adminReviewQueue"] if i["id"] == "review-tbd"]
    if matching:
        assert matching[0]["resolved"] is True


def test_dependencies_endpoint_requires_params(env):
    res = _client(env["admin"]).get(reverse("academics:dependencies"))
    assert res.status_code == 400
