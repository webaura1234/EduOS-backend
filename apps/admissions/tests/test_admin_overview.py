"""Admin Admissions overview aggregate — AdmissionsData shape."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.queries import application as app_q
from apps.admissions.queries import enquiry as enq_q
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school", name="Sriman School")
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch,
                        phone="+919810000001", custom_login_id=None,
                        must_change_password=False)
    return dict(tenant=tenant, branch=branch, admin=admin)


def test_overview_shape(env):
    resp = _client(env["admin"]).get(reverse("admissions:admin-overview"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    for key in ("enquiries", "applications", "funnel", "courses", "intakes",
                "notificationLog", "institutionName", "eligibilityRules"):
        assert key in body, f"missing {key}"
    assert body["institutionName"] == "Sriman School"
    assert set(body["funnel"]) == {"byStage", "bySource", "conversionRate"}


def test_enquiry_and_application_reflected(env):
    enq = enq_q.create_enquiry(
        branch=env["branch"], source="walk_in", applicant_name="Ravi Kumar",
        phone="+919800000000",
    )
    app_q.create_application(branch=env["branch"], enquiry=enq, status="submitted")

    body = _data(_client(env["admin"]).get(reverse("admissions:admin-overview")))
    assert any(e["applicantName"] == "Ravi Kumar" for e in body["enquiries"])
    assert len(body["applications"]) == 1
    app = body["applications"][0]
    assert app["applicantName"] == "Ravi Kumar"
    assert app["stage"] == "documents"   # submitted → documents
    assert app["status"] == "active"
    assert body["funnel"]["byStage"]["enquiry"] == 1
    assert body["funnel"]["bySource"]["walk_in"] == 1


def test_requires_admin(env):
    student = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                          custom_login_id="STU-1", must_change_password=False)
    resp = _client(student).get(reverse("admissions:admin-overview"))
    assert resp.status_code == 403
