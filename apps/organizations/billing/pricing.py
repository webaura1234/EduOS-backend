"""
Unified pricing service — the single source of truth for per-student rates.

Resolution order:
  1. List price per plan (standard/ai) from PlatformPlanDefinition (DB), seeded
     from plan_catalog.py only when the row is missing.
  2. Per-tenant discount_percent from TenantLicensePricing (0 when unset).
  3. Net price = round(list_price * (1 - discount_percent / 100)).

All runtime billing (tenant summaries, student subscriptions, licensing
invoices) should call this module rather than reading plan_catalog constants
directly.
"""

from __future__ import annotations

from apps.organizations.plan_catalog import PLAN_LIMITS, normalize_plan


def list_price_for_plan(plan: str) -> int:
    """Live list price for a plan from the DB catalog; falls back to seed defaults."""
    from apps.organizations.models import PlatformPlanDefinition

    plan = normalize_plan(plan)
    row = PlatformPlanDefinition.objects.filter(plan=plan).only("price_per_student_inr").first()
    if row is not None:
        return row.price_per_student_inr
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["standard"])["pricePerStudentInr"]


def plan_for_tenant(tenant_id) -> str:
    """The tenant's current plan slug (normalized)."""
    from apps.organizations.models import PlanSubscription

    sub = PlanSubscription.objects.filter(tenant_id=tenant_id).only("plan").first()
    return normalize_plan(sub.plan if sub else "standard")


def discount_percent_for_tenant(tenant_id) -> int:
    """Per-tenant discount (0-100); 0 when no active pricing row exists."""
    from apps.organizations.models import TenantLicensePricing

    row = (
        TenantLicensePricing.objects.filter(tenant_id=tenant_id, is_active=True)
        .only("discount_percent")
        .first()
    )
    return row.discount_percent if row else 0


def apply_discount(list_price: int, discount_percent: int) -> int:
    """Net price after discount, rounded to the nearest rupee."""
    pct = max(0, min(100, int(discount_percent)))
    return round(list_price * (1 - pct / 100))


def net_unit_price_inr(tenant_id, plan: str | None = None) -> int:
    """Net per-student price for a tenant on the given plan (defaults to its plan)."""
    from apps.organizations.models import TenantLicensePricing

    row = (
        TenantLicensePricing.objects.filter(tenant_id=tenant_id, is_active=True)
        .only("net_unit_price_inr", "discount_percent")
        .first()
    )
    if row is not None and row.net_unit_price_inr > 0:
        return row.net_unit_price_inr

    resolved_plan = normalize_plan(plan) if plan else plan_for_tenant(tenant_id)
    list_price = list_price_for_plan(resolved_plan)
    return apply_discount(list_price, discount_percent_for_tenant(tenant_id))


def pricing_for_tenant(tenant_id, plan: str | None = None) -> dict:
    """API-facing pricing breakdown for a tenant."""
    resolved_plan = normalize_plan(plan) if plan else plan_for_tenant(tenant_id)
    list_price = list_price_for_plan(resolved_plan)
    discount = discount_percent_for_tenant(tenant_id)
    unit = net_unit_price_inr(tenant_id, resolved_plan)
    return {
        "plan": resolved_plan,
        "listPricePerStudentInr": list_price,
        "discountPercent": discount,
        "unitPricePerStudentInr": unit,
    }


def plan_catalog_for_api() -> list[dict]:
    """DB-backed plan catalog (prices live), matching the frontend PlatformPlanLimits shape."""
    from apps.organizations.queries.platform_ops import get_plan_definitions

    catalog = []
    for definition in get_plan_definitions():
        catalog.append({
            "plan": definition["plan"],
            "label": definition["label"],
            "pricePerStudentInr": definition["pricePerStudentInr"],
            "includedAiCreditsPerStudent": definition["includedAiCreditsPerStudent"],
            "includesAi": definition["includesAi"],
            "description": definition["description"],
        })
    return catalog
