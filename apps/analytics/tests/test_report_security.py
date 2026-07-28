"""Report security — branch-gated detail/download + download audit (4.1–4.3)."""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.academics.tests.factories import AcademicYearFactory
from apps.analytics.enums import ReportStatus, ReportType
from apps.analytics.models import AuditLog
from apps.analytics.permissions import REPORT_DOWNLOADED
from apps.analytics.queries import report as report_q
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
    branch_a = BranchFactory(tenant=tenant, name="Campus A")
    branch_b = BranchFactory(tenant=tenant, name="Campus B")
    today = timezone.localdate()
    year_a = AcademicYearFactory(
        branch=branch_a, name="YA", is_current=True,
        start_date=today - datetime.timedelta(days=100),
        end_date=today + datetime.timedelta(days=100),
    )
    year_b = AcademicYearFactory(
        branch=branch_b, name="YB", is_current=True,
        start_date=today - datetime.timedelta(days=100),
        end_date=today + datetime.timedelta(days=100),
    )
    admin_a = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch_a, phone="+919860000001",
        custom_login_id=None, must_change_password=False,
    )
    admin_b = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch_b, phone="+919860000002",
        custom_login_id=None, must_change_password=False,
    )
    return dict(
        tenant=tenant,
        branch_a=branch_a,
        branch_b=branch_b,
        year_a=year_a,
        year_b=year_b,
        admin_a=admin_a,
        admin_b=admin_b,
    )


def _ready_export(*, tenant, branch, requester, report_type=ReportType.FEE_COLLECTION):
    export = report_q.create_export(
        tenant=tenant,
        branch=branch,
        report_type=report_type,
        params={"academicYearId": "x"},
        requested_by=requester,
    )
    report_q.update_export(export, {
        "status": ReportStatus.READY,
        "snapshot": {"rows": [{"batchName": "A", "totalInvoiced": 1}]},
        "row_count": 1,
    })
    export.refresh_from_db()
    return export


def test_admin_cannot_detail_other_branch_export(env):
    export_b = _ready_export(
        tenant=env["tenant"], branch=env["branch_b"], requester=env["admin_b"],
    )
    resp = _client(env["admin_a"]).get(
        reverse("analytics:report-detail", kwargs={"export_id": export_b.pk}),
    )
    assert resp.status_code == 404


def test_admin_cannot_download_other_branch_export(env):
    export_b = _ready_export(
        tenant=env["tenant"], branch=env["branch_b"], requester=env["admin_b"],
    )
    before = AuditLog.objects.filter(action=REPORT_DOWNLOADED).count()
    resp = _client(env["admin_a"]).get(
        reverse("analytics:report-download", kwargs={"export_id": export_b.pk}),
    )
    assert resp.status_code == 404
    assert AuditLog.objects.filter(action=REPORT_DOWNLOADED).count() == before


def test_admin_can_download_own_branch_export(env):
    export_a = _ready_export(
        tenant=env["tenant"], branch=env["branch_a"], requester=env["admin_a"],
    )
    resp = _client(env["admin_a"]).get(
        reverse("analytics:report-download", kwargs={"export_id": export_a.pk}),
        REMOTE_ADDR="203.0.113.10",
    )
    assert resp.status_code == 200
    assert "text/csv" in resp["Content-Type"]


def test_admin_can_download_export_they_requested_on_other_branch(env):
    # Requester exception: admin_a requested an export tagged to branch_b
    export = _ready_export(
        tenant=env["tenant"], branch=env["branch_b"], requester=env["admin_a"],
    )
    resp = _client(env["admin_a"]).get(
        reverse("analytics:report-download", kwargs={"export_id": export.pk}),
    )
    assert resp.status_code == 200


def test_successful_download_writes_audit_row(env):
    export_a = _ready_export(
        tenant=env["tenant"], branch=env["branch_a"], requester=env["admin_a"],
    )
    resp = _client(env["admin_a"]).get(
        reverse("analytics:report-download", kwargs={"export_id": export_a.pk}),
        REMOTE_ADDR="198.51.100.7",
    )
    assert resp.status_code == 200
    row = AuditLog.objects.filter(
        action=REPORT_DOWNLOADED, entity_id=str(export_a.pk),
    ).first()
    assert row is not None
    assert row.actor_user_id == env["admin_a"].pk
    assert row.diff.get("reportType") == ReportType.FEE_COLLECTION
    assert row.ip_address is not None
