"""Report lifecycle — async aggregations, filenames, retention, retry (5.2, 6.1–6.3, 7.1)."""

import datetime
from unittest.mock import patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.academics.tests.factories import AcademicYearFactory
from apps.analytics.enums import ReportStatus, ReportType
from apps.analytics.interactors import report as report_i
from apps.analytics.models import ReportExport
from apps.analytics.queries import report as report_q
from apps.analytics.tasks import generate_export_task, purge_expired_exports
from apps.core.exports.base import ACADEMIC_YEAR_FILTER, BATCH_FILTER
from apps.core.exports.filename import build_download_filename
from apps.core.exports.params import filter_specs_to_dict
from apps.core.exports.registry import get_definition
from apps.core.exports.retention import export_expires_at
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


@pytest.fixture(autouse=True)
def _clear_s3():
    SandboxS3.SINK.clear()
    SandboxS3.CONTENT_TYPES.clear()
    yield
    SandboxS3.SINK.clear()
    SandboxS3.CONTENT_TYPES.clear()


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant, name="CMR-Lalgadi")
    today = timezone.localdate()
    year = AcademicYearFactory(
        branch=branch, name="2026-27", is_current=True,
        start_date=today - datetime.timedelta(days=100),
        end_date=today + datetime.timedelta(days=100),
    )
    admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919870000001",
        custom_login_id=None, must_change_password=False,
    )
    other_branch = BranchFactory(tenant=tenant, name="Other Campus")
    other_admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=other_branch, phone="+919870000002",
        custom_login_id=None, must_change_password=False,
    )
    return dict(
        tenant=tenant, branch=branch, year=year, admin=admin,
        other_branch=other_branch, other_admin=other_admin,
    )


def test_aggregation_generate_queues_without_resolve_on_request(env):
    definition = get_definition(ReportType.ADMISSION_FUNNEL)
    with patch.object(definition, "resolve_rows", side_effect=AssertionError("must not run inline")):
        with patch("apps.analytics.tasks.generate_export_task.delay") as delay:
            export = report_i.generate_report(
                tenant=env["tenant"],
                branch=env["branch"],
                report_type=ReportType.ADMISSION_FUNNEL,
                params={"academicYearId": str(env["year"].pk)},
                requester=env["admin"],
            )
    assert export.status == ReportStatus.QUEUED
    delay.assert_called_once_with(str(export.pk))


def test_generate_export_task_soft_timeout_marks_timed_out(env):
    from apps.core.exports.base import AggregationExportDefinition, Column

    export = report_q.create_export(
        tenant=env["tenant"],
        branch=env["branch"],
        report_type=ReportType.ADMISSION_FUNNEL,
        params={"academicYearId": str(env["year"].pk)},
        requested_by=env["admin"],
    )
    report_q.update_export(export, {"status": ReportStatus.QUEUED})

    class FakeAgg(AggregationExportDefinition):
        report_type = ReportType.ADMISSION_FUNNEL
        title = "x"

        def resolve_rows(self, *, tenant, branch, params):
            raise SoftTimeLimitExceeded()

        def get_columns(self, params):
            return [Column("a", "A")]

    with patch("apps.analytics.tasks._try_get_definition", return_value=FakeAgg()):
        generate_export_task.run(str(export.pk))

    export.refresh_from_db()
    assert export.status == ReportStatus.TIMED_OUT
    assert "time budget" in export.error.lower()


@override_settings(REPORT_EXPORT_RETENTION_DAYS=90)
def test_export_expires_at_uses_retention_days():
    before = timezone.now()
    expires = export_expires_at()
    delta = expires - before
    assert datetime.timedelta(days=89) < delta < datetime.timedelta(days=91)


def test_download_filename_uses_definition_and_branch(env):
    definition = get_definition(ReportType.FEE_LEDGER)
    export = report_q.create_export(
        tenant=env["tenant"],
        branch=env["branch"],
        report_type=ReportType.FEE_LEDGER,
        params={"fromDate": "2026-07-13"},
        requested_by=env["admin"],
    )
    name = build_download_filename(definition, export=export, params=export.params)
    assert name.startswith("fee-ledger_2026-07-13_")
    assert "CMR-Lalgadi" in name
    assert name.endswith(".csv")
    assert str(export.pk) not in name


def test_download_content_disposition_is_descriptive(env):
    export = report_q.create_export(
        tenant=env["tenant"],
        branch=env["branch"],
        report_type=ReportType.FEE_LEDGER,
        params={"fromDate": "2026-07-13"},
        requested_by=env["admin"],
    )
    report_q.update_export(export, {
        "status": ReportStatus.READY,
        "snapshot": {"rows": [{"a": 1}]},
        "row_count": 1,
        "expires_at": timezone.now() + datetime.timedelta(days=30),
    })
    resp = _client(env["admin"]).get(
        reverse("analytics:report-download", kwargs={"export_id": export.pk}),
    )
    assert resp.status_code == 200
    cd = resp["Content-Disposition"]
    assert "fee-ledger" in cd
    assert str(export.pk) not in cd


def test_purge_soft_expires_keeps_row_deletes_s3(env):
    export = report_q.create_export(
        tenant=env["tenant"],
        branch=env["branch"],
        report_type=ReportType.FEE_COLLECTION,
        params={},
        requested_by=env["admin"],
    )
    key = f"exports/{env['tenant'].pk}/{export.pk}.csv"
    SandboxS3.SINK[key] = b"a,b\n1,2\n"
    report_q.update_export(export, {
        "status": ReportStatus.READY,
        "file_key": key,
        "download_url": "https://sandbox-s3.local/x",
        "expires_at": timezone.now() - datetime.timedelta(hours=1),
        "snapshot": {"rows": [{"x": 1}]},
    })
    purge_expired_exports()
    export.refresh_from_db()
    assert ReportExport.objects.filter(pk=export.pk).exists()
    assert export.status == ReportStatus.EXPIRED
    assert export.file_key == ""
    assert key not in SandboxS3.SINK


def test_download_expired_returns_410(env):
    export = report_q.create_export(
        tenant=env["tenant"],
        branch=env["branch"],
        report_type=ReportType.FEE_COLLECTION,
        params={},
        requested_by=env["admin"],
    )
    report_q.update_export(export, {
        "status": ReportStatus.READY,
        "snapshot": {"rows": [{"a": 1}]},
        "expires_at": timezone.now() - datetime.timedelta(minutes=1),
    })
    resp = _client(env["admin"]).get(
        reverse("analytics:report-download", kwargs={"export_id": export.pk}),
    )
    assert resp.status_code == 410
    body = resp.json()
    msg = body.get("message") or body.get("error") or ""
    assert "expired" in str(msg).lower()


def test_retry_failed_export_requeues(env):
    export = report_q.create_export(
        tenant=env["tenant"],
        branch=env["branch"],
        report_type=ReportType.ADMISSION_FUNNEL,
        params={"academicYearId": str(env["year"].pk)},
        requested_by=env["admin"],
    )
    report_q.update_export(export, {
        "status": ReportStatus.FAILED,
        "error": "boom",
        "file_key": "old",
        "snapshot": {"rows": [{"stale": True}]},
    })
    with patch("apps.analytics.tasks.generate_export_task.delay") as delay:
        resp = _client(env["admin"]).post(
            reverse("analytics:report-retry", kwargs={"export_id": export.pk}),
        )
    assert resp.status_code == 200
    body = _data(resp)["report"]
    assert body["status"] == ReportStatus.QUEUED
    export.refresh_from_db()
    assert export.error == ""
    assert export.file_key == ""
    assert "rows" not in (export.snapshot or {})
    delay.assert_called_once_with(str(export.pk))


def test_retry_ready_returns_409(env):
    export = report_q.create_export(
        tenant=env["tenant"],
        branch=env["branch"],
        report_type=ReportType.FEE_COLLECTION,
        params={},
        requested_by=env["admin"],
    )
    report_q.update_export(export, {"status": ReportStatus.READY})
    resp = _client(env["admin"]).post(
        reverse("analytics:report-retry", kwargs={"export_id": export.pk}),
    )
    assert resp.status_code == 409


def test_retry_cross_branch_returns_404(env):
    export = report_q.create_export(
        tenant=env["tenant"],
        branch=env["branch"],
        report_type=ReportType.FEE_COLLECTION,
        params={},
        requested_by=env["admin"],
    )
    report_q.update_export(export, {"status": ReportStatus.FAILED, "error": "x"})
    resp = _client(env["other_admin"]).post(
        reverse("analytics:report-retry", kwargs={"export_id": export.pk}),
    )
    assert resp.status_code == 404


def test_catalog_filters_include_group(env):
    resp = _client(env["admin"]).get(reverse("analytics:report-catalog"))
    assert resp.status_code == 200
    fee = next(r for r in _data(resp)["reports"] if r["id"] == ReportType.FEE_LEDGER)
    year_f = next(f for f in fee["filters"] if f["key"] == "academicYearId")
    status_f = next(f for f in fee["filters"] if f["key"] == "status")
    assert year_f.get("group") == "scope"
    assert status_f.get("group") == "criteria"


def test_filter_specs_to_dict_includes_group():
    rows = filter_specs_to_dict([ACADEMIC_YEAR_FILTER, BATCH_FILTER])
    assert rows[0]["group"] == "scope"
    assert rows[1]["group"] == "scope"


def test_saved_filter_round_trip_with_branch_id(env):
    client = _client(env["admin"])
    create = client.post(
        reverse("analytics:report-saved-filters"),
        {
            "reportType": ReportType.FEE_LEDGER,
            "name": "My campus",
            "params": {
                "academicYearId": str(env["year"].pk),
                "branchId": str(env["branch"].pk),
            },
        },
        format="json",
    )
    assert create.status_code == 201
    filt = _data(create)["filter"]
    assert filt["params"]["branchId"] == str(env["branch"].pk)

    listed = client.get(
        reverse("analytics:report-saved-filters"),
        {"reportType": ReportType.FEE_LEDGER},
    )
    assert listed.status_code == 200
    row = next(f for f in _data(listed)["filters"] if f["id"] == filt["id"])
    assert row["params"]["branchId"] == str(env["branch"].pk)
