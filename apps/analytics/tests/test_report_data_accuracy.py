"""Report data accuracy — academic-year isolation, CSV column labels, soft-delete default."""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.admissions.models import StudentEnrollment
from apps.admissions.queries.enquiry import create_enquiry
from apps.analytics.enums import ReportStatus, ReportType
from apps.analytics.interactors import report as report_i
from apps.analytics.tasks import rows_to_csv_bytes
from apps.core.exports.base import Column
from apps.core.exports.registry import get_definition
from apps.fees.enums import InvoiceStatus
from apps.fees.models import FeeInvoice
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
    today = timezone.localdate()
    year_a = AcademicYearFactory(
        branch=branch,
        name="Prior Year",
        is_current=False,
        start_date=today - datetime.timedelta(days=700),
        end_date=today - datetime.timedelta(days=400),
    )
    year_b = AcademicYearFactory(
        branch=branch,
        name="Current Year",
        is_current=True,
        start_date=today - datetime.timedelta(days=180),
        end_date=today + datetime.timedelta(days=180),
    )
    admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919840000001",
        custom_login_id=None, must_change_password=False,
    )
    return dict(
        tenant=tenant, branch=branch, year_a=year_a, year_b=year_b, admin=admin,
    )


def _enrollment(env, *, year, login_id):
    batch = BatchFactory(course__department__branch=env["branch"], academic_year=year)
    student = UserFactory(
        role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
        custom_login_id=login_id, must_change_password=False,
    )
    profile = StudentProfile.objects.create(
        user=student, current_batch=batch, academic_status=AcademicStatus.ACTIVE,
    )
    return StudentEnrollment.objects.create(
        branch=env["branch"], student_profile=profile, batch=batch, academic_year=year,
    )


def test_fee_ledger_isolates_by_academic_year(env):
    enr_a = _enrollment(env, year=env["year_a"], login_id="STU-A")
    enr_b = _enrollment(env, year=env["year_b"], login_id="STU-B")
    FeeInvoice.objects.create(
        branch=env["branch"], student=enr_a,
        total_paise=10000, paid_paise=0, status=InvoiceStatus.DUE,
    )
    FeeInvoice.objects.create(
        branch=env["branch"], student=enr_b,
        total_paise=20000, paid_paise=0, status=InvoiceStatus.DUE,
    )

    export_a = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"],
        report_type=ReportType.FEE_LEDGER,
        params={"academicYearId": str(env["year_a"].pk)},
        requester=env["admin"],
        threshold=10_000,
    )
    export_b = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"],
        report_type=ReportType.FEE_LEDGER,
        params={"academicYearId": str(env["year_b"].pk)},
        requester=env["admin"],
        threshold=10_000,
    )
    assert export_a.row_count == 1
    assert export_b.row_count == 1
    assert export_a.snapshot["rows"][0]["amount"] != export_b.snapshot["rows"][0]["amount"]


def test_fee_ledger_defaults_to_current_year(env):
    enr_a = _enrollment(env, year=env["year_a"], login_id="STU-OLD")
    enr_b = _enrollment(env, year=env["year_b"], login_id="STU-CUR")
    FeeInvoice.objects.create(
        branch=env["branch"], student=enr_a,
        total_paise=10000, paid_paise=0, status=InvoiceStatus.DUE,
    )
    FeeInvoice.objects.create(
        branch=env["branch"], student=enr_b,
        total_paise=20000, paid_paise=0, status=InvoiceStatus.DUE,
    )
    export = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"],
        report_type=ReportType.FEE_LEDGER,
        params={},
        requester=env["admin"],
        threshold=10_000,
    )
    assert export.row_count == 1
    assert export.params.get("academicYearId") == str(env["year_b"].pk)


def test_admission_funnel_scopes_by_year_dates(env):
    # Enquiry inside year B window
    create_enquiry(branch=env["branch"], source="walk_in", applicant_name="InRange")
    # Enquiry outside year B — force created_at into year A window
    old = create_enquiry(branch=env["branch"], source="walk_in", applicant_name="OutOfRange")
    mid_a = env["year_a"].start_date + datetime.timedelta(days=10)
    Enquiry = old.__class__
    Enquiry.objects.filter(pk=old.pk).update(
        created_at=timezone.make_aware(datetime.datetime.combine(mid_a, datetime.time(12, 0))),
    )

    export = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"],
        report_type=ReportType.ADMISSION_FUNNEL,
        params={"academicYearId": str(env["year_b"].pk)},
        requester=env["admin"],
    )
    rows = {r["stage"]: r["students"] for r in export.snapshot["rows"]}
    assert rows.get("New Enquiries", 0) == 1

    export_a = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"],
        report_type=ReportType.ADMISSION_FUNNEL,
        params={"academicYearId": str(env["year_a"].pk)},
        requester=env["admin"],
    )
    rows_a = {r["stage"]: r["students"] for r in export_a.snapshot["rows"]}
    assert rows_a.get("New Enquiries", 0) == 1


def test_snapshot_download_uses_column_labels(env):
    export = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"],
        report_type=ReportType.ADMISSION_FUNNEL,
        params={"academicYearId": str(env["year_b"].pk)},
        requester=env["admin"],
    )
    # Simulate missing file_key so download rebuilds from snapshot
    from apps.analytics.queries import report as report_q
    report_q.update_export(export, {"file_key": "", "download_url": ""})
    export.refresh_from_db()

    resp = _client(env["admin"]).get(
        reverse("analytics:report-download", kwargs={"export_id": export.pk}),
    )
    assert resp.status_code == 200
    csv_text = resp.content.decode("utf-8-sig")
    header = csv_text.splitlines()[0]
    assert "Stage" in header
    assert "Students" in header
    assert "stage" not in header.split(",")  # camelCase keys must not be headers


def test_rows_to_csv_bytes_accepts_columns():
    rows = [{"stage": "New", "students": 3}]
    columns = [Column("stage", "Stage"), Column("students", "Students")]
    content = rows_to_csv_bytes(rows, columns).decode("utf-8-sig")
    assert content.startswith("Stage,Students")


def test_soft_deleted_invoice_excluded_from_fee_ledger(env):
    enr = _enrollment(env, year=env["year_b"], login_id="STU-SOFT")
    active = FeeInvoice.objects.create(
        branch=env["branch"], student=enr,
        total_paise=10000, paid_paise=0, status=InvoiceStatus.DUE, is_active=True,
    )
    deleted = FeeInvoice.objects.create(
        branch=env["branch"], student=enr,
        total_paise=5000, paid_paise=0, status=InvoiceStatus.DUE, is_active=False,
    )
    definition = get_definition(ReportType.FEE_LEDGER)
    qs = definition.get_queryset_for_export(
        tenant_id=env["tenant"].pk,
        branch_id=env["branch"].pk,
        params={"academicYearId": str(env["year_b"].pk)},
    )
    ids = set(qs.values_list("pk", flat=True))
    assert active.pk in ids
    assert deleted.pk not in ids


def test_catalog_includes_academic_years(env):
    resp = _client(env["admin"]).get(reverse("analytics:report-catalog"))
    assert resp.status_code == 200
    body = _data(resp)
    assert "academicYears" in body
    years = body["academicYears"]
    assert any(y.get("isCurrent") for y in years)
    fee_ledger = next(r for r in body["reports"] if r["id"] == ReportType.FEE_LEDGER)
    ay_filter = next(f for f in fee_ledger["filters"] if f["key"] == "academicYearId")
    assert ay_filter["type"] == "academic_year_id"
    assert ay_filter["required"] is True
