"""Analytics tests — audit hash-chain, dashboards + scoping, report exports (Celery+S3), NAAC."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.queries.enquiry import create_enquiry
from apps.analytics.enums import ReportStatus, ReportType
from apps.analytics.interactors import audit as audit_i
from apps.analytics.interactors import report as report_i
from apps.analytics.models import AuditLog
from apps.integrations.adapters.s3 import SandboxS3
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
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919830000001",
                        custom_login_id=None, must_change_password=False)
    super_admin = UserFactory(role=Role.SUPER_ADMIN, tenant=tenant, branch=branch,
                              phone="+919830000002", custom_login_id=None,
                              must_change_password=False)
    return dict(tenant=tenant, branch=branch, admin=admin, super_admin=super_admin)


# ── Audit hash chain (F-239 / EC-PRIV-06) ─────────────────────────────────────
def test_audit_chain_links_and_verifies(env):
    a = audit_i.record_audit(tenant=env["tenant"], actor=env["admin"], action="result.publish",
                             entity_type="Exam", entity_id="e1", diff={"x": 1})
    b = audit_i.record_audit(tenant=env["tenant"], actor=env["admin"], action="payroll.run",
                             entity_type="PayrollRun", entity_id="r1", diff={"y": 2})
    assert a.prev_hash == ""              # first row in the chain
    assert b.prev_hash == a.row_hash      # chained to the previous
    assert audit_i.verify_chain(env["tenant"].pk) == {"valid": True, "verified": 2}


def test_audit_tamper_detected(env):
    audit_i.record_audit(tenant=env["tenant"], actor=env["admin"], action="refund.create",
                         entity_type="Refund", entity_id="rf1", diff={"amt": 100})
    row = AuditLog.objects.filter(tenant=env["tenant"]).first()
    # Tamper directly (bypassing the append-only queries layer) → chain must break.
    AuditLog.objects.filter(pk=row.pk).update(diff={"amt": 999})
    result = audit_i.verify_chain(env["tenant"].pk)
    assert result["valid"] is False
    assert result["brokenAt"] == str(row.pk)


def test_audit_list_endpoint(env):
    audit_i.record_audit(tenant=env["tenant"], actor=env["admin"], action="rollover.execute",
                         entity_type="Branch", entity_id=str(env["branch"].pk))
    resp = _client(env["admin"]).get(reverse("analytics:audit-list"))
    assert resp.status_code == 200
    assert len(_data(resp)["audit"]) == 1
    assert _data(resp)["audit"][0]["action"] == "rollover.execute"


# ── Dashboards + scoping ──────────────────────────────────────────────────────
def test_admin_dashboard_shape(env):
    resp = _client(env["admin"]).get(reverse("analytics:dashboard-admin"))
    assert resp.status_code == 200
    body = _data(resp)
    assert "fees" in body and "alerts" in body and "admissionsFunnel" in body
    assert resp["X-Cache-Age"] == "0"
    assert "lastUpdated" in body


def test_super_admin_dashboard_rolls_up(env):
    resp = _client(env["super_admin"]).get(reverse("analytics:dashboard-super-admin"))
    assert resp.status_code == 200
    body = _data(resp)
    assert body["totals"]["branches"] >= 1
    assert isinstance(body["branchComparison"], list)


def test_super_admin_dashboard_denied_to_admin(env):
    resp = _client(env["admin"]).get(reverse("analytics:dashboard-super-admin"))
    assert resp.status_code == 403


def test_student_dashboard_shape(env):
    from apps.accounts.models.profile import StudentProfile
    student = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"], must_change_password=False)
    StudentProfile.objects.create(user=student)

    resp = _client(student).get(reverse("analytics:dashboard-student"))
    assert resp.status_code == 200
    body = _data(resp)
    assert body["institutionType"] == "school"
    assert body["profile"]["name"] == student.full_name
    assert body["attendancePercent"] == 0
    assert body["attendanceThreshold"] == 75
    assert isinstance(body["scheduleToday"], list)
    assert body["upcomingExamsCount"] == 0


def test_student_dashboard_no_profile(env):
    student = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"], must_change_password=False)
    resp = _client(student).get(reverse("analytics:dashboard-student"))
    assert resp.status_code == 200
    body = _data(resp)
    assert body["institutionType"] == "school"
    assert body["profile"]["name"] == student.full_name
    assert body["attendancePercent"] == 0
    assert body["attendanceThreshold"] == 75
    assert isinstance(body["scheduleToday"], list)
    assert body["upcomingExamsCount"] == 0


def test_student_dashboard_denied_to_admin(env):
    resp = _client(env["admin"]).get(reverse("analytics:dashboard-student"))
    assert resp.status_code == 403


# ── Reports: inline snapshot, large→Celery+S3, snapshot immutability, NAAC ─────
def test_small_report_inline_snapshot(env):
    create_enquiry(branch=env["branch"], source="walk_in", applicant_name="Asha")
    resp = _client(env["admin"]).post(reverse("analytics:report-create"),
                                      {"reportType": ReportType.ADMISSION_FUNNEL}, format="json")
    assert resp.status_code == 201, resp.content
    report = _data(resp)["report"]
    assert report["status"] == ReportStatus.READY
    assert report["rowCount"] >= 1


def test_large_report_runs_celery_and_uploads_to_s3(env):
    create_enquiry(branch=env["branch"], source="walk_in", applicant_name="Asha")
    # threshold=0 forces the large/background path (Celery runs eagerly in tests).
    export = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"], report_type=ReportType.ADMISSION_FUNNEL,
        params={}, requester=env["admin"], threshold=0,
    )
    assert export.status == ReportStatus.READY
    assert export.file_key
    assert export.download_url.startswith("https://sandbox-s3.local/")
    assert export.file_key in SandboxS3.SINK  # the CSV was "uploaded"


def test_report_snapshot_is_frozen(env):
    create_enquiry(branch=env["branch"], source="walk_in", applicant_name="Asha")
    export = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"], report_type=ReportType.ADMISSION_FUNNEL,
        params={}, requester=env["admin"],
    )
    before = export.row_count
    # Data changes AFTER the report was generated → the frozen snapshot must not change (F-064).
    create_enquiry(branch=env["branch"], source="online", applicant_name="Ben")
    export.refresh_from_db()
    assert export.row_count == before


def test_naac_export_lists_gaps(env):
    resp = _client(env["admin"]).get(reverse("analytics:report-naac"))
    assert resp.status_code == 200
    body = _data(resp)
    assert "data" in body and isinstance(body["missingFields"], list)
    assert len(body["missingFields"]) >= 1
