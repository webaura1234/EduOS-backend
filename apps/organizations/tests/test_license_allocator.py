"""License allocator — the 10 business cases from the licensing design.

One license = one student, consumed forever. FIFO conversion on payment.
"""

import pytest

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.organizations.billing import license_allocator as alloc
from apps.organizations.enums import (
    LicenseInvoiceType,
    StudentLicenseStatus,
)
from apps.organizations.models import (
    LicensePayment,
    StudentLicense,
    TenantLicenseSummary,
)
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return TenantFactory(subdomain="lic-school")


@pytest.fixture
def branch(tenant):
    return BranchFactory(tenant=tenant)


def _pay(tenant, n, **kw):
    return alloc.record_payment(
        tenant,
        licenses_granted=n,
        amount_inr=n * 499,
        payment_mode="cash",
        **kw,
    )


def _enroll(tenant, branch, n=1):
    rows = []
    for i in range(n):
        student = UserFactory(
            role=Role.STUDENT, tenant=tenant, branch=branch,
            custom_login_id=None, phone=None, email=None,
        )
        rows.append(alloc.on_student_enrolled(student))
    return rows


def _summary(tenant) -> TenantLicenseSummary:
    return TenantLicenseSummary.objects.get(tenant=tenant)


def test_case1_purchase_500_add_500_all_licensed(tenant, branch):
    _pay(tenant, 5)
    rows = _enroll(tenant, branch, 5)

    assert all(r.license_status == StudentLicenseStatus.LICENSED for r in rows)
    s = _summary(tenant)
    assert s.licenses_purchased == 5
    assert s.licenses_consumed == 5
    assert s.unlicensed_active_count == 0
    assert s.pending_amount_inr == 0


def test_case2_over_limit_students_become_unlicensed(tenant, branch):
    _pay(tenant, 5)
    _enroll(tenant, branch, 5)
    extra = _enroll(tenant, branch, 2)

    assert all(r.license_status == StudentLicenseStatus.UNLICENSED for r in extra)
    s = _summary(tenant)
    assert s.licenses_consumed == 5
    assert s.unlicensed_active_count == 2
    assert s.pending_amount_inr == 2 * 499


def test_case3_payment_converts_unlicensed_fifo(tenant, branch):
    _pay(tenant, 2)
    _enroll(tenant, branch, 4)  # 2 licensed, 2 unlicensed
    _pay(tenant, 2)

    s = _summary(tenant)
    assert s.licenses_purchased == 4
    assert s.licenses_consumed == 4
    assert s.unlicensed_active_count == 0
    assert StudentLicense.objects.filter(
        tenant=tenant, license_status=StudentLicenseStatus.UNLICENSED,
    ).count() == 0


def test_case4_deleting_licensed_student_keeps_license_consumed(tenant, branch):
    _pay(tenant, 3)
    rows = _enroll(tenant, branch, 3)

    victim = rows[0]
    alloc.on_student_lifecycle_event(
        victim.student_user, "student_deleted", detail="hard delete",
    )
    victim.refresh_from_db()

    assert victim.licensed_at is not None
    s = _summary(tenant)
    assert s.licenses_consumed == 3  # never decrements


def test_case5_new_students_after_capacity_are_unlicensed(tenant, branch):
    _pay(tenant, 2)
    _enroll(tenant, branch, 2)
    new = _enroll(tenant, branch, 2)

    assert all(r.license_status == StudentLicenseStatus.UNLICENSED for r in new)
    assert _summary(tenant).unlicensed_active_count == 2


def test_case6_partial_payment_converts_exactly_n_oldest(tenant, branch):
    rows = _enroll(tenant, branch, 5)  # no purchase yet: 5 unlicensed
    _pay(tenant, 2)

    for r in rows:
        r.refresh_from_db()
    licensed = [r for r in rows if r.license_status == StudentLicenseStatus.LICENSED]
    unlicensed = [r for r in rows if r.license_status == StudentLicenseStatus.UNLICENSED]
    assert len(licensed) == 2
    assert len(unlicensed) == 3
    # FIFO: the two oldest enrolled_at got the licenses.
    ordered = sorted(rows, key=lambda r: r.enrolled_at)
    assert [r.pk for r in ordered[:2]] == sorted(
        [r.pk for r in licensed],
        key=lambda pk: next(x.enrolled_at for x in rows if x.pk == pk),
    )
    assert _summary(tenant).pending_amount_inr == 3 * 499


def test_case7_withdrawn_student_license_stays_consumed(tenant, branch):
    _pay(tenant, 1)
    row = _enroll(tenant, branch, 1)[0]
    alloc.on_student_lifecycle_event(
        row.student_user, "student_withdrawn", detail="left school",
    )
    row.refresh_from_db()
    assert row.license_status == StudentLicenseStatus.LICENSED
    assert _summary(tenant).licenses_consumed == 1


def test_case7b_withdrawn_unlicensed_student_reduces_pending(tenant, branch):
    row = _enroll(tenant, branch, 1)[0]
    assert _summary(tenant).pending_amount_inr == 499
    alloc.on_student_lifecycle_event(
        row.student_user, "student_withdrawn", detail="left before payment",
    )
    s = _summary(tenant)
    assert s.unlicensed_active_count == 0
    assert s.pending_amount_inr == 0


def test_case8_restored_student_keeps_existing_license(tenant, branch):
    _pay(tenant, 1)
    row = _enroll(tenant, branch, 1)[0]
    first_licensed_at = row.licensed_at

    # Re-enrolling (restore) returns the same row; licensed_at unchanged.
    again = alloc.on_student_enrolled(row.student_user)
    assert again.pk == row.pk
    assert again.licensed_at == first_licensed_at
    assert _summary(tenant).licenses_consumed == 1


def test_case9_merge_never_decrements_consumed(tenant, branch):
    _pay(tenant, 1)
    keep = _enroll(tenant, branch, 1)[0]        # licensed
    dupe = _enroll(tenant, branch, 1)[0]        # unlicensed duplicate

    alloc.on_student_lifecycle_event(
        dupe.student_user, "duplicate_merged", detail=f"merged into {keep.pk}",
    )
    s = _summary(tenant)
    assert s.licenses_consumed == 1
    keep.refresh_from_db()
    assert keep.license_status == StudentLicenseStatus.LICENSED


def test_case10_renewal_invoice_uses_total_consumed(tenant, branch):
    _pay(tenant, 3)
    _enroll(tenant, branch, 3)
    # One student leaves — consumed stays 3.
    row = StudentLicense.objects.filter(tenant=tenant).first()
    alloc.on_student_lifecycle_event(row.student_user, "student_withdrawn")

    invoice = alloc.generate_invoice(tenant, invoice_type=LicenseInvoiceType.RENEWAL)
    assert invoice.licenses_count == 3
    assert invoice.amount_inr == 3 * 499


def test_idempotency_key_prevents_double_payment(tenant, branch):
    _enroll(tenant, branch, 2)
    p1 = _pay(tenant, 1, idempotency_key="pay-abc")
    p2 = _pay(tenant, 1, idempotency_key="pay-abc")

    assert p1.pk == p2.pk
    assert LicensePayment.objects.filter(tenant=tenant).count() == 1
    assert _summary(tenant).licenses_purchased == 1


def test_surplus_licenses_cover_future_enrollments(tenant, branch):
    _pay(tenant, 3)
    rows = _enroll(tenant, branch, 2)
    assert all(r.license_status == StudentLicenseStatus.LICENSED for r in rows)
    s = _summary(tenant)
    assert s.licenses_purchased == 3
    assert s.licenses_consumed == 2

    third = _enroll(tenant, branch, 1)[0]
    assert third.license_status == StudentLicenseStatus.LICENSED
    assert _summary(tenant).licenses_consumed == 3


def test_extend_period_to_june(tenant, branch):
    import datetime

    period = alloc.ensure_period(tenant)
    new_end = datetime.date(period.end_date.year, 6, 30)
    alloc.extend_period(period, new_end)
    period.refresh_from_db()
    assert period.end_date == new_end


def test_ensure_period_syncs_plan_valid_until(tenant):
    from apps.organizations.models import PlanSubscription

    PlanSubscription.objects.create(tenant=tenant)
    period = alloc.ensure_period(tenant)

    sub = PlanSubscription.objects.get(tenant=tenant)
    assert sub.valid_until == period.end_date
    assert sub.next_due_at.date() == period.end_date


def test_expiry_pipeline_grace_then_expired(tenant, branch):
    import datetime

    from django.utils import timezone

    from apps.organizations.enums import SubscriptionPeriodStatus
    from apps.organizations.policies.student_access import get_student_access

    today = timezone.localdate()
    period = alloc.ensure_period(tenant)
    _pay(tenant, 1)
    row = _enroll(tenant, branch, 1)[0]
    assert get_student_access(row.student_user)["blockedModules"] == []

    period.start_date = today - datetime.timedelta(days=400)
    period.end_date = today - datetime.timedelta(days=1)
    period.save(update_fields=["start_date", "end_date"])

    result = alloc.run_expiry_pipeline()
    assert result["movedToGrace"] == 1
    period.refresh_from_db()
    assert period.status == SubscriptionPeriodStatus.GRACE
    assert period.grace_ends_at == period.end_date + datetime.timedelta(days=alloc.GRACE_DAYS)
    # Grace = warning only; a licensed student is still not blocked.
    assert get_student_access(row.student_user)["blockedModules"] == []

    # Past the grace window → expired, and even licensed students get blocked.
    period.grace_ends_at = today - datetime.timedelta(days=1)
    period.save(update_fields=["grace_ends_at"])
    result = alloc.run_expiry_pipeline()
    assert result["expired"] == 1
    period.refresh_from_db()
    assert period.status == SubscriptionPeriodStatus.EXPIRED

    access = get_student_access(row.student_user)
    assert access["subscriptionStatus"] == "expired"
    assert len(access["blockedModules"]) > 0


def test_branch_scoped_payment_only_converts_that_branch(tenant):
    branch_a = BranchFactory(tenant=tenant, name="Campus A")
    branch_b = BranchFactory(tenant=tenant, name="Campus B")
    for _ in range(2):
        student = UserFactory(
            role=Role.STUDENT, tenant=tenant, branch=branch_a,
            custom_login_id=None, phone=None, email=None,
        )
        alloc.on_student_enrolled(student)
    for _ in range(2):
        student = UserFactory(
            role=Role.STUDENT, tenant=tenant, branch=branch_b,
            custom_login_id=None, phone=None, email=None,
        )
        alloc.on_student_enrolled(student)

    assert StudentLicense.objects.filter(
        tenant=tenant, license_status=StudentLicenseStatus.UNLICENSED,
    ).count() == 4

    alloc.record_payment(
        tenant, licenses_granted=1, amount_inr=499, payment_mode="cash",
        branch_id=branch_a.pk,
    )

    assert StudentLicense.objects.filter(
        branch=branch_a, license_status=StudentLicenseStatus.LICENSED,
    ).count() == 1
    assert StudentLicense.objects.filter(
        branch=branch_a, license_status=StudentLicenseStatus.UNLICENSED,
    ).count() == 1
    assert StudentLicense.objects.filter(
        branch=branch_b, license_status=StudentLicenseStatus.UNLICENSED,
    ).count() == 2


def test_tenant_wide_payment_ignores_branch(tenant, branch):
    branch_b = BranchFactory(tenant=tenant, name="Campus B")
    for b in (branch, branch_b):
        student = UserFactory(
            role=Role.STUDENT, tenant=tenant, branch=b,
            custom_login_id=None, phone=None, email=None,
        )
        alloc.on_student_enrolled(student)

    alloc.record_payment(tenant, licenses_granted=1, amount_inr=499, payment_mode="cash")

    licensed = StudentLicense.objects.filter(
        tenant=tenant, license_status=StudentLicenseStatus.LICENSED,
    ).count()
    assert licensed == 1
    assert StudentLicense.objects.filter(
        tenant=tenant, license_status=StudentLicenseStatus.UNLICENSED,
    ).count() == 1


def test_invalid_branch_id_raises(tenant):
    with pytest.raises(ValueError, match="Branch not found"):
        alloc.record_payment(
            tenant, licenses_granted=1, amount_inr=499, payment_mode="cash",
            branch_id="00000000-0000-0000-0000-000000000099",
        )
