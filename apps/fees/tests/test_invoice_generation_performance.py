"""Query-count regression test for bulk invoice generation.

generate_invoices_for_batch used to run ~6+ queries per student (assignment
lookup/creation, invoice-exists check, billing guardian) plus one INSERT per
invoice line/installment. It's now batched to a fixed number of queries
regardless of batch size.
"""

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.admissions.models import StudentEnrollment
from apps.fees.enums import InvoiceStatus
from apps.fees.interactors import generate_invoices_for_batch
from apps.fees.models import FeeInvoice, FeeStructure

pytestmark = pytest.mark.django_db


def _make_students(tenant, branch, batch, academic_year, n, offset):
    students = []
    for i in range(n):
        user = UserFactory(
            role=Role.STUDENT, tenant=tenant, branch=branch,
            custom_login_id=f"STU-INV-{offset + i}", must_change_password=False,
        )
        profile = StudentProfile.objects.create(
            user=user, current_batch=batch, academic_status=AcademicStatus.ACTIVE,
        )
        enrollment = StudentEnrollment.objects.create(
            branch=branch, student_profile=profile, batch=batch, academic_year=academic_year,
        )
        students.append(enrollment)
    return students


def test_generate_invoices_query_count_does_not_scale_with_batch_size(branch, batch, academic_year):
    tenant = branch.tenant
    fs = FeeStructure.objects.create(
        branch=branch, academic_year=academic_year, name="Grade 10 General",
        components=[
            {"kind": "tuition", "label": "Tuition", "amount_paise": 5000000,
             "installment_no": 1, "due_date": "2024-07-10"},
            {"kind": "transport", "label": "Transport", "amount_paise": 1000000,
             "installment_no": 2, "due_date": "2024-09-10"},
        ],
    )

    _make_students(tenant, branch, batch, academic_year, 5, 0)
    with CaptureQueriesContext(connection) as ctx_small:
        invoices_small = generate_invoices_for_batch(
            branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs,
        )
    assert len(invoices_small) == 5
    queries_small = len(ctx_small.captured_queries)

    fs2 = FeeStructure.objects.create(
        branch=branch, academic_year=academic_year, name="Grade 10 General 2",
        components=[
            {"kind": "tuition", "label": "Tuition", "amount_paise": 5000000,
             "installment_no": 1, "due_date": "2024-07-10"},
            {"kind": "transport", "label": "Transport", "amount_paise": 1000000,
             "installment_no": 2, "due_date": "2024-09-10"},
        ],
    )
    _make_students(tenant, branch, batch, academic_year, 100, 1000)
    with CaptureQueriesContext(connection) as ctx_big:
        invoices_big = generate_invoices_for_batch(
            branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs2,
        )
    # 105 students now in the batch (5 existing + 100 new) all need an fs2 invoice.
    assert len(invoices_big) == 105
    queries_big = len(ctx_big.captured_queries)

    for inv in invoices_big:
        assert inv.total_paise == 6000000
        assert inv.status == InvoiceStatus.DUE
        assert inv.lines.count() == 2
        assert inv.installments.count() == 2

    # SQLite's bulk_create() auto-chunks a statement once row-count * field-count
    # crosses its ~999-variable-per-statement limit, so a few extra INSERT
    # statements at 105 rows is expected (each chunk, not each row) — this
    # tolerance still rejects any reintroduced per-student query (that would add
    # ~1 query per extra student, i.e. ~100 for the 100 extra students here).
    assert queries_big <= queries_small + 10, (
        f"generate_invoices_for_batch query count scales with batch size: {queries_small} -> {queries_big}"
    )


def test_generate_invoices_skips_already_invoiced_students(branch, batch, academic_year):
    tenant = branch.tenant
    fs = FeeStructure.objects.create(
        branch=branch, academic_year=academic_year, name="Grade 10 General",
        components=[
            {"kind": "tuition", "label": "Tuition", "amount_paise": 5000000,
             "installment_no": 1, "due_date": "2024-07-10"},
        ],
    )
    _make_students(tenant, branch, batch, academic_year, 4, 5000)
    first = generate_invoices_for_batch(
        branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs,
    )
    assert len(first) == 4
    # Re-running for the same batch/structure must not create duplicate invoices.
    second = generate_invoices_for_batch(
        branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs,
    )
    assert len(second) == 0
    assert FeeInvoice.objects.filter(assignment__fee_structure=fs).count() == 4
