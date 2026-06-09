"""
Plan presenter — maps PlanSubscription to the frontend `SuperAdminPlanData` shape.

Some display attributes (price, billing cycle, feature list, branch limit) are not
yet persisted on the subscription; they are derived from the plan tier here so the
endpoint is contract-complete. Move them onto the model when billing is built.
"""

# Per-tier display metadata (placeholder economics — tune against real pricing).
_TIER_META = {
    "starter": {"priceInrPerMonth": 4000, "branches": 1,
                "features": ["Core SIS", "Attendance", "Fees", "Communications"]},
    "growth": {"priceInrPerMonth": 12000, "branches": 5,
               "features": ["Everything in Starter", "Admissions", "Timetable", "HR & Payroll", "Exam analytics"]},
    "enterprise": {"priceInrPerMonth": 30000, "branches": 99,
                   "features": ["Everything in Growth", "AI generation", "NAAC/NIRF", "API & SSO", "White-label"]},
}


def plan_data_dict(subscription) -> dict:
    """Present a PlanSubscription as `{ current, requests }` (camelCase)."""
    if subscription is None:
        return {"current": None, "requests": []}

    meta = _TIER_META.get(subscription.plan, _TIER_META["starter"])
    started = subscription.created_at
    return {
        "current": {
            "tier": subscription.plan,
            "billingCycle": "annual",
            "priceInrPerMonth": meta["priceInrPerMonth"],
            "startedAt": started.isoformat() if started else None,
            "renewsAt": subscription.valid_until.isoformat() if subscription.valid_until else None,
            "limits": {
                "branches": meta["branches"],
                "students": subscription.student_limit,
                "storageGb": subscription.storage_limit_gb,
            },
            "features": meta["features"],
            "billingStatus": subscription.billing_status,
        },
        # Upgrade-request workflow is not modelled yet — return an empty list.
        "requests": [],
    }
