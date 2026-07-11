"""Tests for the configurable enquiry form: builder save + public submission."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.admissions.interactors import enquiry_form as form_i
from apps.admissions.models import Enquiry, EnquiryForm
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db

ADMIN_URL = "/api/v1/admissions/enquiry-form/"
PUBLIC_FORM_URL = "/api/v1/admissions/public/enquiry-form/"
PUBLIC_SUBMIT_URL = "/api/v1/admissions/public/enquiry/"


def _admin_setup():
    tenant = TenantFactory(subdomain="greenfield")
    branch = BranchFactory(tenant=tenant, is_primary=True)
    admin = UserFactory(tenant=tenant, branch=branch, role=Role.ADMIN)
    client = APIClient()
    client.force_authenticate(user=admin)
    return client, branch, tenant


# ── Interactor ───────────────────────────────────────────────────────────────

def test_save_form_normalises_and_dedupes_keys():
    branch = BranchFactory(tenant=TenantFactory())
    form = form_i.save_form(
        branch, title="Apply", description="", is_public=True,
        fields=[
            {"label": "Parent Name", "type": "text", "required": True},
            {"label": "Parent Name", "type": "text"},  # dup label → unique key
        ],
    )
    keys = [f["key"] for f in form.fields]
    assert keys == ["parent-name", "parent-name_2"]


def test_validate_submission_enforces_required_and_types():
    branch = BranchFactory(tenant=TenantFactory())
    form = form_i.save_form(
        branch, title="Apply", description="", is_public=True,
        fields=[
            {"label": "Prior School", "type": "text", "required": True},
            {"label": "Grade", "type": "select", "required": False, "options": ["6", "7"]},
        ],
    )
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        form_i.validate_submission(form, {"grade": "6"})  # missing required prior-school

    with pytest.raises(ValidationError):
        form_i.validate_submission(form, {"prior-school": "St X", "grade": "9"})  # bad choice

    cleaned = form_i.validate_submission(form, {"prior-school": "St X", "grade": "7"})
    assert cleaned == {"prior-school": "St X", "grade": "7"}


# ── Admin endpoint ───────────────────────────────────────────────────────────

def test_admin_get_creates_default_form():
    client, _, _ = _admin_setup()
    res = client.get(ADMIN_URL)
    assert res.status_code == 200
    assert res.data["title"]
    assert res.data["fields"] == []


def test_admin_put_saves_fields():
    client, branch, _ = _admin_setup()
    res = client.put(
        ADMIN_URL,
        {
            "title": "Admission Enquiry 2026",
            "description": "Apply now",
            "isPublic": True,
            "fields": [{"label": "Previous School", "type": "text", "required": True}],
        },
        format="json",
    )
    assert res.status_code == 200
    assert res.data["fields"][0]["key"] == "previous-school"
    assert EnquiryForm.objects.get(branch=branch).title == "Admission Enquiry 2026"


def test_admin_put_rejects_select_without_options():
    client, _, _ = _admin_setup()
    res = client.put(
        ADMIN_URL,
        {"title": "X", "description": "", "isPublic": True,
         "fields": [{"label": "Grade", "type": "select", "options": []}]},
        format="json",
    )
    assert res.status_code == 400


# ── Public endpoints ─────────────────────────────────────────────────────────

def test_public_get_form_schema():
    client, branch, tenant = _admin_setup()
    form_i.save_form(branch, title="Apply", description="Hi", is_public=True,
                     fields=[{"label": "City", "type": "text"}])
    anon = APIClient()
    res = anon.get(PUBLIC_FORM_URL, {"subdomain": "greenfield"})
    assert res.status_code == 200
    assert res.data["institutionName"] == tenant.name
    assert res.data["fields"][0]["label"] == "City"


def test_public_submit_creates_enquiry():
    client, branch, _ = _admin_setup()
    form_i.save_form(branch, title="Apply", description="", is_public=True,
                     fields=[{"label": "City", "type": "text", "required": True}])
    anon = APIClient()
    res = anon.post(
        PUBLIC_SUBMIT_URL,
        {"subdomain": "greenfield", "applicantName": "Riya", "phone": "+919812345678",
         "customFields": {"city": "Pune"}},
        format="json",
    )
    assert res.status_code == 201
    e = Enquiry.objects.get(branch=branch)
    assert e.applicant_name == "Riya"
    assert e.is_public_submission is True
    assert e.custom_fields == {"city": "Pune"}


def test_public_submit_requires_name_and_phone():
    client, branch, _ = _admin_setup()
    anon = APIClient()
    res = anon.post(PUBLIC_SUBMIT_URL, {"subdomain": "greenfield", "applicantName": ""}, format="json")
    assert res.status_code == 400


def test_public_submit_honeypot_silently_drops():
    client, branch, _ = _admin_setup()
    anon = APIClient()
    res = anon.post(
        PUBLIC_SUBMIT_URL,
        {"subdomain": "greenfield", "applicantName": "Bot", "phone": "1", "_hp": "spam"},
        format="json",
    )
    assert res.status_code == 201
    assert not Enquiry.objects.filter(branch=branch).exists()


def test_public_submit_unknown_subdomain_404():
    anon = APIClient()
    res = anon.post(PUBLIC_SUBMIT_URL, {"subdomain": "nope", "applicantName": "A", "phone": "1"}, format="json")
    assert res.status_code == 404


def test_public_form_disabled_returns_403():
    client, branch, _ = _admin_setup()
    form_i.save_form(branch, title="Apply", description="", is_public=False, fields=[])
    anon = APIClient()
    assert anon.get(PUBLIC_FORM_URL, {"subdomain": "greenfield"}).status_code == 403
