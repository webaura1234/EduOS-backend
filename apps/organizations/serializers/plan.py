"""
Plan presenter — maps PlanSubscription to the frontend `SuperAdminPlanData` shape.
"""

from apps.organizations.plan_catalog import PLAN_LIMITS, normalize_plan

_CORE_ERP_FEATURES = [
    "Core SIS",
    "Attendance",
    "Fees",
    "Communications",
    "Admissions",
    "Timetable",
    "HR & Payroll",
    "Examinations",
    "Library",
    "Transport",
    "Gallery",
]

_AI_FEATURES = [
    "AI assistant",
    "AI insights",
    "AI reports",
    "AI analytics",
    "AI automation",
    "Predictive analytics",
]


def plan_data_dict(subscription) -> dict:
    """Present a PlanSubscription as `{ current, requests }` (camelCase)."""
    if subscription is None:
        return {"current": None, "requests": []}

    plan = normalize_plan(subscription.plan)
    catalog = PLAN_LIMITS.get(plan, PLAN_LIMITS["standard"])
    features = list(_CORE_ERP_FEATURES)
    if catalog.get("includesAi"):
        features.extend(_AI_FEATURES)

    started = subscription.created_at
    return {
        "current": {
            "tier": plan,
            "billingCycle": "annual",
            "priceInrPerStudentYear": catalog.get("pricePerStudentInr", 299),
            "startedAt": started.isoformat() if started else None,
            "renewsAt": subscription.valid_until.isoformat() if subscription.valid_until else None,
            "limits": {
                "branches": None,
                "students": None,
                "storageGb": None,
            },
            "features": features,
            "billingStatus": subscription.billing_status,
            "includesAi": catalog.get("includesAi", False),
            "includedAiCreditsPerStudent": catalog.get("includedAiCreditsPerStudent", 0),
        },
        "requests": [],
    }
