"""
Canonical two-plan catalog — Standard ERP vs AI ERP.

All core ERP modules are included on both plans. The only product difference is
AI capability (gated by plan + per-student AI credits).
"""

from apps.organizations.enums import LEGACY_TO_CURRENT_PLAN, PlanType

PLAN_ORDER = [PlanType.STANDARD, PlanType.AI]

# Per-student annual list price (INR).
PLAN_PRICE_PER_STUDENT_INR: dict[str, int] = {
    PlanType.STANDARD: 299,
    PlanType.AI: 499,
}

# Included AI credits granted per student per academic year on the AI plan.
DEFAULT_INCLUDED_AI_CREDITS_PER_STUDENT = 50

PLAN_LIMITS: dict[str, dict] = {
    PlanType.STANDARD: {
        "label": "Standard ERP",
        "pricePerStudentInr": PLAN_PRICE_PER_STUDENT_INR[PlanType.STANDARD],
        "includedAiCreditsPerStudent": 0,
        "includesAi": False,
        "description": (
            "Full core ERP for every school — all modules, no student/branch caps."
        ),
    },
    PlanType.AI: {
        "label": "AI ERP",
        "pricePerStudentInr": PLAN_PRICE_PER_STUDENT_INR[PlanType.AI],
        "includedAiCreditsPerStudent": DEFAULT_INCLUDED_AI_CREDITS_PER_STUDENT,
        "includesAi": True,
        "description": (
            "Everything in Standard ERP plus AI assistant, insights, reports, "
            "and automation. Includes per-student AI credits; recharge when exceeded."
        ),
    },
}


def normalize_plan(plan: str | None) -> str:
    """Map legacy starter/growth/enterprise slugs to standard/ai."""
    if not plan:
        return PlanType.STANDARD
    if plan in PLAN_LIMITS:
        return plan
    return LEGACY_TO_CURRENT_PLAN.get(plan, PlanType.STANDARD)
