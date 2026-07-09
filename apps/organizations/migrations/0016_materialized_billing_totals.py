"""Materialized billing totals and persisted net unit price."""

from django.db import migrations, models
from django.db.models import Sum

from apps.organizations.plan_catalog import PLAN_LIMITS, normalize_plan


def _list_price(plan_slug, PlatformPlanDefinition):
    plan = normalize_plan(plan_slug)
    row = PlatformPlanDefinition.objects.filter(plan=plan).first()
    if row is not None:
        return row.price_per_student_inr
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["standard"])["pricePerStudentInr"]


def _apply_discount(list_price, discount_percent):
    pct = max(0, min(100, int(discount_percent)))
    return round(list_price * (1 - pct / 100))


def backfill_materialized_billing(apps, schema_editor):
    Tenant = apps.get_model("organizations", "Tenant")
    TenantLicensePricing = apps.get_model("organizations", "TenantLicensePricing")
    TenantLicenseSummary = apps.get_model("organizations", "TenantLicenseSummary")
    PlanSubscription = apps.get_model("organizations", "PlanSubscription")
    StudentPlatformSubscription = apps.get_model("organizations", "StudentPlatformSubscription")
    PlatformPlanDefinition = apps.get_model("organizations", "PlatformPlanDefinition")
    StudentLicense = apps.get_model("organizations", "StudentLicense")

    for tenant in Tenant.objects.filter(is_active=True):
        sub = PlanSubscription.objects.filter(tenant_id=tenant.pk).first()
        plan = normalize_plan(sub.plan if sub else "standard")
        list_price = _list_price(plan, PlatformPlanDefinition)

        pricing_row, _ = TenantLicensePricing.objects.get_or_create(tenant=tenant)
        net_unit = _apply_discount(list_price, pricing_row.discount_percent)
        pricing_row.net_unit_price_inr = net_unit
        pricing_row.save(update_fields=["net_unit_price_inr"])

        StudentPlatformSubscription.objects.filter(
            tenant_id=tenant.pk,
            is_active=True,
        ).update(annual_fee_inr=net_unit, plan=plan)

        active_count = StudentPlatformSubscription.objects.filter(
            tenant_id=tenant.pk,
            is_active=True,
        ).count()
        collected = (
            StudentPlatformSubscription.objects.filter(
                tenant_id=tenant.pk,
                is_active=True,
                status="paid",
            ).aggregate(total=Sum("annual_fee_inr"))["total"]
            or 0
        )
        unlicensed = StudentLicense.objects.filter(
            tenant_id=tenant.pk,
            license_status="unlicensed",
            student_user__is_active=True,
        ).count()

        summary, _ = TenantLicenseSummary.objects.get_or_create(tenant=tenant)
        summary.active_student_count = active_count
        summary.annual_subscription_inr = active_count * net_unit
        summary.collected_subscription_inr = int(collected)
        summary.pending_amount_inr = unlicensed * net_unit
        summary.save(
            update_fields=[
                "active_student_count",
                "annual_subscription_inr",
                "collected_subscription_inr",
                "pending_amount_inr",
            ],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0015_tenant_discount_percent"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantlicensepricing",
            name="net_unit_price_inr",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Persisted net per-student price after discount; refreshed on pricing changes.",
            ),
        ),
        migrations.AddField(
            model_name="tenantlicensesummary",
            name="active_student_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="tenantlicensesummary",
            name="annual_subscription_inr",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="tenantlicensesummary",
            name="collected_subscription_inr",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(backfill_materialized_billing, migrations.RunPython.noop),
    ]
