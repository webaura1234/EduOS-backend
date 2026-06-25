"""Queries — LeaveBalance + LeaveApplication (all ORM here)."""

import datetime
from decimal import Decimal

from django.db.models import Count, Q, Sum

from apps.hr.enums import LeaveStatus
from apps.hr.models import LeaveApplication, LeaveBalance


# ── Balances ──────────────────────────────────────────────────────────────────
def get_or_create_balance(*, employee, leave_type, year, accrual_rate=Decimal("0"),
                          opening=Decimal("0"), user=None) -> LeaveBalance:
    bal, created = LeaveBalance.objects.get_or_create(
        employee=employee, leave_type=leave_type, year=year,
        defaults=dict(balance_days=opening, accrual_rate=accrual_rate,
                      created_by=user, updated_by=user),
    )
    return bal


def get_balance_for_update(employee_id, leave_type, year) -> LeaveBalance | None:
    """Row-locked balance fetch to prevent double-spend on concurrent decisions."""
    return (
        LeaveBalance.objects.select_for_update()
        .filter(employee_id=employee_id, leave_type=leave_type, year=year, is_active=True)
        .first()
    )


def list_balances(employee_id):
    return LeaveBalance.objects.filter(employee_id=employee_id, is_active=True)


def adjust_balance(balance: LeaveBalance, delta, user=None) -> LeaveBalance:
    balance.balance_days = balance.balance_days + delta
    if user:
        balance.updated_by = user
    balance.save(update_fields=["balance_days", "updated_by", "updated_at"])
    return balance


# ── Applications ──────────────────────────────────────────────────────────────
def get_application(branch_id, application_id) -> LeaveApplication | None:
    try:
        return LeaveApplication.objects.select_related("employee", "employee__user", "approver").get(
            employee__branch_id=branch_id, pk=application_id, is_active=True
        )
    except (LeaveApplication.DoesNotExist, ValueError, TypeError):
        return None


def get_application_for_update(application_id) -> LeaveApplication | None:
    return (
        LeaveApplication.objects.select_for_update()
        .filter(pk=application_id, is_active=True)
        .select_related("employee", "employee__user")
        .first()
    )


def list_applications(branch_id, *, status=None, employee_id=None):
    qs = LeaveApplication.objects.filter(
        employee__branch_id=branch_id, is_active=True
    ).select_related("employee", "employee__user", "approver")
    if status:
        qs = qs.filter(status=status)
    if employee_id:
        qs = qs.filter(employee_id=employee_id)
    return qs.order_by("-created_at")


def overlapping_leave(employee_id, from_date, to_date) -> bool:
    return LeaveApplication.objects.filter(
        employee_id=employee_id,
        status__in=[LeaveStatus.PENDING, LeaveStatus.APPROVED],
        is_active=True,
    ).filter(Q(from_date__lte=to_date) & Q(to_date__gte=from_date)).exists()


def create_application(*, employee, leave_type, from_date, to_date, days, reason="",
                       user=None) -> LeaveApplication:
    return LeaveApplication.objects.create(
        employee=employee, leave_type=leave_type, from_date=from_date, to_date=to_date,
        days=days, reason=reason, status=LeaveStatus.PENDING,
        created_by=user, updated_by=user,
    )


def update_application(application: LeaveApplication, fields: dict, expected_version=None,
                       user=None):
    """Version-checked update (EC-API-05/EC-FORM-03)."""
    if expected_version is not None and application.version != expected_version:
        return None, application.version
    for k, v in fields.items():
        setattr(application, k, v)
    application.version += 1
    if user:
        application.updated_by = user
    application.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return application, None


def leave_summary(branch_id) -> dict:
    """F-168 — leave-summary counts by type + status for a branch."""
    rows = (
        LeaveApplication.objects.filter(employee__branch_id=branch_id, is_active=True)
        .values("leave_type", "status")
        .annotate(n=Count("id"), days=Sum("days"))
    )
    return {"rows": list(rows)}


def count_pending_applications(branch_id) -> int:
    return LeaveApplication.objects.filter(
        employee__branch_id=branch_id, status=LeaveStatus.PENDING, is_active=True,
    ).count()


def approved_leave_dates(employee_id, from_date, to_date) -> dict:
    """Expand approved leave applications into date → reason map."""
    apps = LeaveApplication.objects.filter(
        employee_id=employee_id,
        status=LeaveStatus.APPROVED,
        is_active=True,
        from_date__lte=to_date,
        to_date__gte=from_date,
    )
    result: dict = {}
    for app in apps:
        d = max(app.from_date, from_date)
        end = min(app.to_date, to_date)
        while d <= end:
            result[d] = app.reason or "Leave"
            d += datetime.timedelta(days=1)
    return result
