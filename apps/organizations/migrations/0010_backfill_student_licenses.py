"""Backfill StudentLicense rows from the legacy StudentPlatformSubscription table.

- enrolled_at comes from the student's date_joined (stable FIFO order).
- licensed_at is set from paid_at for rows already marked paid.
- A default Apr–Mar subscription period is seeded per tenant.
- TenantLicenseSummary counters are computed from the backfilled rows.
"""

import datetime

from django.db import migrations
from django.utils import timezone


def _default_period_dates(today):
    year = today.year if today.month >= 4 else today.year - 1
    return datetime.date(year, 4, 1), datetime.date(year + 1, 3, 31)


def backfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    StudentPlatformSubscription = apps.get_model("organizations", "StudentPlatformSubscription")
    StudentLicense = apps.get_model("organizations", "StudentLicense")
    TenantSubscriptionPeriod = apps.get_model("organizations", "TenantSubscriptionPeriod")
    TenantLicenseSummary = apps.get_model("organizations", "TenantLicenseSummary")
    Tenant = apps.get_model("organizations", "Tenant")

    today = timezone.localdate()
    start, end = _default_period_dates(today)

    periods = {}
    for tenant in Tenant.objects.all():
        periods[tenant.pk] = TenantSubscriptionPeriod.objects.create(
            tenant=tenant, start_date=start, end_date=end,
            status="active", price_per_student_inr=499,
        )

    # Latest subscription row per student decides initial license status.
    seen = set()
    subs = (
        StudentPlatformSubscription.objects.select_related("student_user")
        .order_by("student_user_id", "-academic_year")
    )
    for sub in subs:
        if sub.student_user_id in seen:
            continue
        seen.add(sub.student_user_id)
        student = sub.student_user
        licensed = sub.status in ("paid", "waived")
        StudentLicense.objects.create(
            tenant_id=sub.tenant_id,
            branch_id=sub.branch_id,
            student_user_id=sub.student_user_id,
            student_name=f"{student.first_name} {student.last_name}".strip(),
            enrolled_at=student.date_joined,
            license_status="licensed" if licensed else "unlicensed",
            licensed_at=(sub.paid_at or student.date_joined) if licensed else None,
            subscription_period=periods.get(sub.tenant_id),
        )

    # Students without any legacy subscription row still get a license row.
    covered = set(StudentLicense.objects.values_list("student_user_id", flat=True))
    for student in User.objects.filter(role="student", tenant__isnull=False):
        if student.pk in covered:
            continue
        StudentLicense.objects.create(
            tenant_id=student.tenant_id,
            branch_id=student.branch_id,
            student_user_id=student.pk,
            student_name=f"{student.first_name} {student.last_name}".strip(),
            enrolled_at=student.date_joined,
            license_status="unlicensed",
            subscription_period=periods.get(student.tenant_id),
        )

    # Summaries: purchased is seeded equal to consumed so existing licensed
    # students remain licensed without inventing payment history.
    for tenant in Tenant.objects.all():
        rows = StudentLicense.objects.filter(tenant=tenant)
        consumed = rows.filter(licensed_at__isnull=False).count()
        unlicensed_active = rows.filter(
            license_status="unlicensed", student_user__is_active=True,
        ).count()
        TenantLicenseSummary.objects.create(
            tenant=tenant,
            licenses_purchased=consumed,
            licenses_consumed=consumed,
            unlicensed_active_count=unlicensed_active,
            pending_amount_inr=unlicensed_active * 499,
            current_period=periods.get(tenant.pk),
        )


def reverse(apps, schema_editor):
    for model in ("TenantLicenseSummary", "StudentLicense", "TenantSubscriptionPeriod"):
        apps.get_model("organizations", model).objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0009_licensing"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(backfill, reverse),
    ]
