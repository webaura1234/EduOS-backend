"""End-to-end HR & Payroll tests — all key F/EC (EC-CEL-01, RBAC, GUARD-15, immutability,
pro-rata, balances)."""

import datetime
import uuid

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.hr.models import Employee, LeaveBalance, Payslip
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db

BASIC = 3000000  # ₹30,000.00
COMPONENTS = [
    {"name": "Basic", "kind": "earning", "calc": "fixed", "amountPaise": BASIC},
    {"name": "HRA", "kind": "earning", "calc": "percent_of_basic", "percent": 40},
    {"name": "PF", "kind": "deduction", "calc": "fixed", "amountPaise": 180000},
]
FULL_NET = 4020000  # (3000000 + 1200000) - 180000


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def _emp(user, branch, *, code, joined=datetime.date(2024, 1, 1), exited=None, components=None):
    return Employee.objects.create(
        user=user, branch=branch, employee_code=code, employment_type="full_time",
        joined_at=joined, exited_at=exited, base_components=components or COMPONENTS,
    )


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919810000001",
                        custom_login_id=None, must_change_password=False)
    fac1_user = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                            custom_login_id="FAC-1", must_change_password=False)
    fac2_user = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                            custom_login_id="FAC-2", must_change_password=False)
    e1 = _emp(fac1_user, branch, code="FAC-1")
    e2 = _emp(fac2_user, branch, code="FAC-2")
    return dict(tenant=tenant, branch=branch, admin=admin, fac1_user=fac1_user,
                fac2_user=fac2_user, e1=e1, e2=e2)


def _run_payroll(env, *, step_up=True, period="2024-09-01", user=None):
    c = _client(user or env["admin"])
    headers = {"HTTP_X_STEP_UP_VERIFIED": "true"} if step_up else {}
    return c.post(reverse("hr:payroll-run"), {"periodMonth": period}, format="json", **headers)


# ── Payroll happy path + money ────────────────────────────────────────────────
def test_payroll_run_creates_payslips(env):
    resp = _run_payroll(env)
    assert resp.status_code == 201, resp.content
    body = _data(resp)
    assert len(body["payslips"]) == 2
    nets = {p["netPaise"] for p in body["payslips"]}
    assert nets == {FULL_NET}
    assert body["payslips"][0]["netRupees"] == "40200.00"
    assert all(p["proRated"] is False for p in body["payslips"])


def test_payroll_requires_step_up(env):
    resp = _run_payroll(env, step_up=False)
    assert resp.status_code == 403
    assert "step_up_required" in resp.content.decode()


def test_duplicate_run_blocked(env):
    assert _run_payroll(env).status_code == 201
    again = _run_payroll(env)
    assert again.status_code == 400
    assert Payslip.objects.count() == 2  # no extra payslips from the rejected run


# ── EC-CEL-01: a mid-run failure rolls back ALL payslips ──────────────────────
def test_ec_cel_01_atomic_rollback(env, monkeypatch):
    from apps.hr.queries import payroll as pay_q

    def boom(**kwargs):
        raise RuntimeError("simulated worker crash")

    monkeypatch.setattr(pay_q, "create_payslip", boom)
    resp = _run_payroll(env)
    assert resp.status_code == 400
    assert Payslip.objects.count() == 0  # nobody half-paid


# ── F-167: pro-rata for mid-month join ────────────────────────────────────────
def test_pro_rata_mid_month_join(env):
    late_user = UserFactory(role=Role.FACULTY, tenant=env["tenant"], branch=env["branch"],
                            custom_login_id="FAC-3", must_change_password=False)
    _emp(late_user, env["branch"], code="FAC-3", joined=datetime.date(2024, 9, 16))
    resp = _run_payroll(env)
    assert resp.status_code == 201
    slips = {p["employeeId"]: p for p in _data(resp)["payslips"]}
    late = next(p for p in slips.values() if p["proRated"] is True)
    assert late["netPaise"] < FULL_NET


# ── F-169: deactivated employee excluded from future payroll ──────────────────
def test_deactivated_excluded_and_rbac07(env):
    # fac1 is ALSO a linked parent (separate user row, shared group).
    group = uuid.uuid4()
    env["fac1_user"].linked_user_group_id = group
    env["fac1_user"].save(update_fields=["linked_user_group_id"])
    parent = UserFactory(role=Role.PARENT, tenant=env["tenant"], branch=env["branch"],
                         phone="+919810000099", custom_login_id=None,
                         linked_user_group_id=group, must_change_password=False)

    headers = {"HTTP_X_STEP_UP_VERIFIED": "true"}
    resp = _client(env["admin"]).post(
        reverse("hr:employee-deactivate", kwargs={"employee_id": str(env["e1"].id)}),
        {}, format="json", **headers)
    assert resp.status_code == 200

    # EC-RBAC-07: only the faculty user is off; the linked parent stays active.
    env["fac1_user"].refresh_from_db()
    parent.refresh_from_db()
    assert env["fac1_user"].is_active is False
    assert parent.is_active is True

    # F-169: next payroll run excludes the deactivated employee (only fac2 remains).
    run = _run_payroll(env)
    assert run.status_code == 201
    assert len(_data(run)["payslips"]) == 1


# ── EC-GUARD-15: payroll executor cannot pay themselves ───────────────────────
def test_ec_guard_15_self_approve_blocked(env):
    # Admin who also draws salary (own Employee record) runs payroll → blocked.
    _emp(env["admin"], env["branch"], code="ADM-1")
    resp = _run_payroll(env)
    assert resp.status_code == 403
    assert "self_approve_blocked" in resp.content.decode()


# ── F-164: immutability — lock blocks edits; EC-RBAC-05 own-only payslip ───────
def test_lock_and_immutability(env):
    run_resp = _run_payroll(env)
    run_id = _data(run_resp)["run"]["id"]
    headers = {"HTTP_X_STEP_UP_VERIFIED": "true"}
    lock = _client(env["admin"]).post(
        reverse("hr:payroll-run-lock", kwargs={"run_id": run_id}), {}, format="json", **headers)
    assert lock.status_code == 200
    assert _data(lock)["run"]["isLocked"] is True

    # Writing a payslip into the locked run is refused at the queries layer (F-164).
    from apps.hr.queries import payroll as pay_q
    from apps.hr.queries.payroll import LockedRunError
    run = pay_q.get_run(env["branch"].id, run_id)
    slip = pay_q.list_payslips_for_run(run.pk).first()
    with pytest.raises(LockedRunError):
        pay_q.update_payslip(slip, {"net_paise": 1})


def test_ec_rbac_05_faculty_sees_only_own_payslip(env):
    run_resp = _run_payroll(env)
    slips = _data(run_resp)["payslips"]
    fac1_slip = next(p for p in slips if p["employeeId"] == str(env["e1"].id))
    fac2_slip = next(p for p in slips if p["employeeId"] == str(env["e2"].id))

    # fac1 can read their own slip but not fac2's.
    c1 = _client(env["fac1_user"])
    assert c1.get(reverse("hr:payslip-detail", kwargs={"payslip_id": fac1_slip["id"]})).status_code == 200
    other = c1.get(reverse("hr:payslip-detail", kwargs={"payslip_id": fac2_slip["id"]}))
    assert other.status_code == 403


# ── Leave: balances, overlap, COI ─────────────────────────────────────────────
def _balance(employee, days=5, leave_type="casual", year="2024-25"):
    return LeaveBalance.objects.create(employee=employee, leave_type=leave_type, year=year,
                                       balance_days=days)


def test_leave_apply_approve_decrements_balance(env):
    _balance(env["e1"], days=5)
    apply = _client(env["fac1_user"]).post(reverse("hr:leave-apply"), {
        "employeeId": str(env["e1"].id), "leaveType": "casual",
        "fromDate": "2024-09-09", "toDate": "2024-09-10", "reason": "personal",
    }, format="json")
    assert apply.status_code == 201, apply.content
    leave_id = _data(apply)["leave"]["id"]
    assert float(_data(apply)["leave"]["days"]) == 2.0

    decide = _client(env["admin"]).patch(
        reverse("hr:leave-decide", kwargs={"application_id": leave_id}),
        {"action": "approve"}, format="json")
    assert decide.status_code == 200
    env["e1"].refresh_from_db()
    bal = LeaveBalance.objects.get(employee=env["e1"], leave_type="casual", year="2024-25")
    assert float(bal.balance_days) == 3.0


def test_leave_insufficient_balance_blocked(env):
    _balance(env["e1"], days=1)
    resp = _client(env["fac1_user"]).post(reverse("hr:leave-apply"), {
        "employeeId": str(env["e1"].id), "leaveType": "casual",
        "fromDate": "2024-09-09", "toDate": "2024-09-13",  # 5 working days > 1
    }, format="json")
    assert resp.status_code == 400


def test_leave_overlap_blocked(env):
    _balance(env["e1"], days=20)
    payload = {"employeeId": str(env["e1"].id), "leaveType": "casual",
               "fromDate": "2024-09-09", "toDate": "2024-09-10"}
    assert _client(env["fac1_user"]).post(reverse("hr:leave-apply"), payload, format="json").status_code == 201
    dup = _client(env["fac1_user"]).post(reverse("hr:leave-apply"), payload, format="json")
    assert dup.status_code == 400


def test_leave_self_approval_blocked_coi(env):
    _balance(env["e1"], days=5)
    apply = _client(env["fac1_user"]).post(reverse("hr:leave-apply"), {
        "employeeId": str(env["e1"].id), "leaveType": "casual",
        "fromDate": "2024-09-09", "toDate": "2024-09-10",
    }, format="json")
    leave_id = _data(apply)["leave"]["id"]
    # fac1 (the applicant) tries to approve their own leave → hard block + auto-route.
    resp = _client(env["fac1_user"]).patch(
        reverse("hr:leave-decide", kwargs={"application_id": leave_id}),
        {"action": "approve"}, format="json")
    assert resp.status_code == 403
    from apps.hr.models import LeaveApplication
    assert LeaveApplication.objects.get(pk=leave_id).auto_routed_coi is True
