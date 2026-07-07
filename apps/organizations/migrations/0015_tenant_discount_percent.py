"""Add per-tenant discount_percent; migrate legacy flat price overrides to a discount."""

from django.db import migrations, models

from apps.organizations.plan_catalog import PLAN_LIMITS, normalize_plan


def flat_price_to_discount(apps, schema_editor):
    """Convert existing flat price_per_student_inr overrides into an equivalent discount.

    Compares the old flat price against the tenant's plan list price; if the flat
    price is lower, store the equivalent discount percent. Otherwise leave at 0.
    """
    TenantLicensePricing = apps.get_model("organizations", "TenantLicensePricing")
    PlanSubscription = apps.get_model("organizations", "PlanSubscription")
    PlatformPlanDefinition = apps.get_model("organizations", "PlatformPlanDefinition")

    def list_price(plan_slug):
        plan = normalize_plan(plan_slug)
        row = PlatformPlanDefinition.objects.filter(plan=plan).first()
        if row is not None:
            return row.price_per_student_inr
        return PLAN_LIMITS.get(plan, PLAN_LIMITS["standard"])["pricePerStudentInr"]

    for row in TenantLicensePricing.objects.all():
        sub = PlanSubscription.objects.filter(tenant_id=row.tenant_id).first()
        plan_slug = sub.plan if sub else "standard"
        base = list_price(plan_slug)
        flat = row.price_per_student_inr or 0
        if base > 0 and 0 < flat < base:
            row.discount_percent = round((1 - flat / base) * 100)
            row.save(update_fields=["discount_percent"])


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0014_two_plan_pricing_ai_credits"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantlicensepricing",
            name="discount_percent",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Discount (0-100) applied to the plan list price for this tenant only.",
            ),
        ),
        migrations.RunPython(flat_price_to_discount, migrations.RunPython.noop),
    ]
