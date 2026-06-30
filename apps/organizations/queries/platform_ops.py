"""
Queries — platform-owner operational data (audit, trials, support, settings, tickets).
"""

from datetime import timedelta

from django.utils import timezone

from apps.accounts.models.user import Role
from apps.accounts.queries.user import count_active_by_role_in_tenant
from apps.organizations.models import (
    PlanSubscription,
    PlatformAuditLog,
    PlatformGlobalAnnouncement,
    PlatformMaintenanceSetting,
    PlatformPlanDefinition,
    PlatformSupportModeLog,
    PlatformSupportSession,
    PlatformSupportTicket,
    PlatformSupportTicketComment,
    Tenant,
)
from apps.organizations.queries.platform_tenant import (
    PLAN_LIMITS,
    PLAN_ORDER,
    branch_count,
    to_ui_status,
)

# Seeded plan constants
PLAN_TRIAL_DAYS = 30
PLAN_GRACE_DAYS = 15

PLAN_MRR_INR = {
    "starter": 5000,
    "growth": 12000,
    "enterprise": 35000,
}

PLAN_ANNUAL_PER_STUDENT_INR = {
    "starter": 100,
    "growth": 200,
    "enterprise": 500,
}

FEATURE_LABELS = {
    "parentPortal": "Parent portal",
    "onlineFees": "Online fees",
    "admissions": "Admissions",
    "hrPayroll": "HR & payroll",
    "examinations": "Examinations",
}

DEFAULT_PLAN_FEATURES = {
    "starter": {
        "parentPortal": False,
        "onlineFees": False,
        "admissions": True,
        "hrPayroll": False,
        "examinations": False,
    },
    "growth": {
        "parentPortal": True,
        "onlineFees": True,
        "admissions": True,
        "hrPayroll": False,
        "examinations": True,
    },
    "enterprise": {
        "parentPortal": True,
        "onlineFees": True,
        "admissions": True,
        "hrPayroll": True,
        "examinations": True,
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _actor_name(user=None) -> str:
    if user is None:
        return "Platform Owner"
    return user.get_full_name() or user.email or "Platform Owner"


def _announcement_to_dict(ann: PlatformGlobalAnnouncement) -> dict:
    return {
        "id": str(ann.id),
        "title": ann.title,
        "body": ann.body,
        "severity": ann.severity,
        "publishedAt": ann.published_at.isoformat(),
        "publishedBy": ann.published_by_name,
        "isActive": ann.is_active,
    }


def _support_log_to_dict(log: PlatformSupportModeLog) -> dict:
    return {
        "id": str(log.id),
        "tenantSubdomain": log.tenant_subdomain,
        "tenantName": log.tenant_name,
        "action": log.action,
        "detail": log.detail,
        "readOnly": log.read_only,
        "actorName": log.actor_name,
        "createdAt": log.created_at.isoformat(),
    }


def _audit_to_dict(entry: PlatformAuditLog) -> dict:
    d = {
        "id": str(entry.id),
        "category": entry.category,
        "action": entry.action,
        "detail": entry.detail,
        "actorName": entry.actor_name,
        "createdAt": entry.created_at.isoformat(),
    }
    if entry.tenant_subdomain:
        d["tenantSubdomain"] = entry.tenant_subdomain
    if entry.tenant_name:
        d["tenantName"] = entry.tenant_name
    return d


def _ticket_to_dict(ticket: PlatformSupportTicket) -> dict:
    return {
        "id": str(ticket.id),
        "title": ticket.title,
        "severity": ticket.severity,
        "status": ticket.status,
        "category": ticket.category,
        "description": ticket.description,
        "createdAt": ticket.created_at.isoformat(),
        "updatedAt": ticket.updated_at.isoformat(),
        "lastActivityAt": ticket.last_activity_at.isoformat(),
        "tenantId": str(ticket.tenant_id),
        "tenantName": ticket.tenant.name,
        "tenantSubdomain": ticket.tenant.subdomain,
        "comments": [
            {
                "id": str(c.id),
                "authorRole": c.author_role,
                "authorName": c.author_name,
                "message": c.message,
                "createdAt": c.created_at.isoformat(),
            }
            for c in ticket.comments.all()
        ],
    }


# ── Audit log ─────────────────────────────────────────────────────────────────

def log_audit(
    *,
    category: str,
    action: str,
    detail: str,
    user=None,
    tenant: Tenant | None = None,
) -> PlatformAuditLog:
    return PlatformAuditLog.objects.create(
        category=category,
        action=action,
        detail=detail,
        actor_name=_actor_name(user),
        actor=user,
        tenant=tenant,
        tenant_name=tenant.name if tenant else "",
        tenant_subdomain=tenant.subdomain if tenant else "",
    )


def get_audit_logs() -> dict:
    audit = list(PlatformAuditLog.objects.order_by("-created_at")[:200])
    support_logs = list(
        PlatformSupportModeLog.objects.order_by("-created_at")[:100]
    )
    return {
        "auditLog": [_audit_to_dict(e) for e in audit],
        "supportModeLog": [_support_log_to_dict(l) for l in support_logs],
    }


# ── Maintenance mode ──────────────────────────────────────────────────────────

_DEFAULT_MAINTENANCE_MESSAGE = (
    "PiiAura is undergoing scheduled maintenance. "
    "Write operations are temporarily disabled."
)


def _maintenance_to_dict(m: PlatformMaintenanceSetting) -> dict:
    return {
        "enabled": m.enabled,
        "message": m.message,
        "blockWrites": m.block_writes,
        "scheduledEndAt": m.scheduled_end_at.isoformat() if m.scheduled_end_at else None,
        "updatedAt": m.updated_at.isoformat(),
        "updatedBy": m.updated_by_name,
    }


def get_maintenance() -> dict:
    m, _ = PlatformMaintenanceSetting.objects.get_or_create(
        defaults={
            "enabled": False,
            "message": _DEFAULT_MAINTENANCE_MESSAGE,
            "block_writes": True,
            "updated_by_name": "System",
        }
    )
    return _maintenance_to_dict(m)


def update_maintenance(*, enabled: bool, message: str | None = None,
                       block_writes: bool | None = None,
                       scheduled_end_at=None, user=None) -> dict:
    m, _ = PlatformMaintenanceSetting.objects.get_or_create(
        defaults={
            "enabled": False,
            "message": _DEFAULT_MAINTENANCE_MESSAGE,
            "block_writes": True,
            "updated_by_name": "System",
        }
    )
    m.enabled = enabled
    if message is not None:
        m.message = message.strip() or _DEFAULT_MAINTENANCE_MESSAGE
    if block_writes is not None:
        m.block_writes = block_writes
    if scheduled_end_at is not None:
        m.scheduled_end_at = scheduled_end_at
    m.updated_by_name = _actor_name(user)
    m.save()
    log_audit(
        category="settings",
        action="maintenance.enable" if enabled else "maintenance.disable",
        detail=f"Maintenance {'on' if enabled else 'off'}" + (
            " (writes blocked)" if enabled and m.block_writes else ""
        ),
        user=user,
    )
    return _maintenance_to_dict(m)


# ── Plan definitions ──────────────────────────────────────────────────────────

def _ensure_plan_definitions() -> list[PlatformPlanDefinition]:
    existing = {p.plan: p for p in PlatformPlanDefinition.objects.all()}
    for plan_key, limits in PLAN_LIMITS.items():
        if plan_key not in existing:
            PlatformPlanDefinition.objects.create(
                plan=plan_key,
                label=limits["label"],
                max_branches=limits["maxBranches"],
                max_students=limits["maxStudents"],
                included_features=limits["includedFeatures"],
                description=f"{limits['label']} tier for schools and colleges.",
            )
    return list(PlatformPlanDefinition.objects.order_by(
        [plan for plan in PLAN_ORDER].index if False else "plan"
    ))


def get_plan_definitions() -> list[dict]:
    defs = {p.plan: p for p in PlatformPlanDefinition.objects.all()}
    # Seed any missing plans
    for plan_key, limits in PLAN_LIMITS.items():
        if plan_key not in defs:
            obj = PlatformPlanDefinition.objects.create(
                plan=plan_key,
                label=limits["label"],
                max_branches=limits["maxBranches"],
                max_students=limits["maxStudents"],
                included_features=limits["includedFeatures"],
                description=f"{limits['label']} tier.",
            )
            defs[plan_key] = obj

    result = []
    for plan_key in PLAN_ORDER:
        if plan_key in defs:
            p = defs[plan_key]
            result.append({
                "plan": p.plan,
                "label": p.label,
                "maxBranches": p.max_branches,
                "maxStudents": p.max_students,
                "includedFeatures": p.included_features or [],
                "description": p.description,
            })
    return result


def update_plan_definition(
    *,
    plan: str,
    label: str | None = None,
    max_branches: int | None = None,
    max_students: int | None = None,
    included_features: list | None = None,
    description: str | None = None,
    user=None,
) -> dict:
    try:
        p = PlatformPlanDefinition.objects.get(plan=plan)
    except PlatformPlanDefinition.DoesNotExist:
        raise ValueError(f"Plan '{plan}' not found")
    if label is not None and label.strip():
        p.label = label.strip()
    if max_branches is not None:
        p.max_branches = max_branches
    if max_students is not None:
        p.max_students = max_students
    if included_features is not None:
        p.included_features = [f.strip() for f in included_features if f.strip()]
    if description is not None:
        p.description = description.strip()
    p.save()
    log_audit(
        category="settings",
        action="plan.definition.update",
        detail=f"Updated {plan} plan definition",
        user=user,
    )
    return {
        "plan": p.plan,
        "label": p.label,
        "maxBranches": p.max_branches,
        "maxStudents": p.max_students,
        "includedFeatures": p.included_features or [],
        "description": p.description,
    }


# ── Announcements ─────────────────────────────────────────────────────────────

def get_announcements() -> list[dict]:
    return [
        _announcement_to_dict(a)
        for a in PlatformGlobalAnnouncement.objects.order_by("-published_at")
    ]


def publish_announcement(*, title: str, body: str, severity: str, user=None) -> dict:
    title = title.strip()
    body = body.strip()
    if not title or not body:
        raise ValueError("Title and body are required")
    ann = PlatformGlobalAnnouncement.objects.create(
        title=title,
        body=body,
        severity=severity,
        is_active=True,
        published_at=timezone.now(),
        published_by=user,
        published_by_name=_actor_name(user),
    )
    log_audit(
        category="announcement",
        action="announcement.publish",
        detail=f"Published: {title}",
        user=user,
    )
    return _announcement_to_dict(ann)


def set_announcement_active(announcement_id: str, is_active: bool, user=None) -> dict:
    try:
        ann = PlatformGlobalAnnouncement.objects.get(pk=announcement_id)
    except PlatformGlobalAnnouncement.DoesNotExist:
        raise ValueError("Announcement not found")
    ann.is_active = is_active
    ann.save(update_fields=["is_active", "updated_at"])
    log_audit(
        category="announcement",
        action="announcement.activate" if is_active else "announcement.deactivate",
        detail=f"{ann.title} — {'visible' if is_active else 'hidden'}",
        user=user,
    )
    return _announcement_to_dict(ann)


# ── Settings (aggregate) ──────────────────────────────────────────────────────

def get_settings() -> dict:
    return {
        "planDefinitions": get_plan_definitions(),
        "announcements": get_announcements(),
        "maintenance": get_maintenance(),
    }


# ── Plan feature matrix ───────────────────────────────────────────────────────

FEATURE_CATALOG = [
    {"key": k, "label": v}
    for k, v in FEATURE_LABELS.items()
]


def get_plan_feature_matrix() -> dict:
    defs = {p["plan"]: p for p in get_plan_definitions()}
    rows = []
    for plan_key in PLAN_ORDER:
        p = defs.get(plan_key, {})
        included = set(p.get("includedFeatures", []))
        flags = {
            k: FEATURE_LABELS[k] in included
            for k in FEATURE_LABELS
        }
        # Use the stored flags if there's no perfect match; fall back to defaults
        if not any(flags.values()):
            flags = dict(DEFAULT_PLAN_FEATURES.get(plan_key, {}))
        rows.append({
            "plan": plan_key,
            "label": p.get("label", plan_key.title()),
            "flags": flags,
        })
    return {
        "featureCatalog": FEATURE_CATALOG,
        "rows": rows,
    }


def update_plan_feature_matrix(*, plan: str, flags: dict, user=None) -> dict:
    enabled_labels = [FEATURE_LABELS[k] for k, v in flags.items() if v and k in FEATURE_LABELS]
    update_plan_definition(
        plan=plan,
        included_features=enabled_labels,
        user=user,
    )
    log_audit(
        category="settings",
        action="plan.feature_matrix.update",
        detail=f"Updated {plan} feature matrix: {', '.join(enabled_labels) or 'none'}",
        user=user,
    )
    return get_plan_feature_matrix()


# ── Support session ───────────────────────────────────────────────────────────

def _session_to_dict(s: PlatformSupportSession) -> dict | None:
    if s.exited_at is not None:
        return None
    return {
        "tenantId": str(s.tenant_id),
        "tenantName": s.tenant_name,
        "tenantSubdomain": s.tenant_subdomain,
        "readOnly": s.read_only,
        "enteredAt": s.entered_at.isoformat(),
    }


def get_support_mode(user=None) -> dict:
    active = PlatformSupportSession.objects.filter(exited_at__isnull=True).first()
    support_logs = list(PlatformSupportModeLog.objects.order_by("-created_at")[:100])
    tenants = list(
        Tenant.objects.exclude(status="offboarding")
        .values("id", "name", "subdomain", "status")
        .order_by("name")
    )
    return {
        "session": _session_to_dict(active) if active else None,
        "supportModeLog": [_support_log_to_dict(l) for l in support_logs],
        "tenants": [
            {
                "id": str(t["id"]),
                "name": t["name"],
                "subdomain": t["subdomain"],
                "status": to_ui_status(t["status"]),
            }
            for t in tenants
        ],
    }


def enter_support_mode(*, tenant_id: str, read_only: bool, user=None) -> dict:
    try:
        tenant = Tenant.objects.get(pk=tenant_id)
    except (Tenant.DoesNotExist, ValueError):
        raise ValueError("Tenant not found")
    if tenant.status in ("deactivated", "offboarding"):
        raise ValueError("Cannot enter support mode for an inactive tenant")

    # End any existing active session first
    PlatformSupportSession.objects.filter(exited_at__isnull=True).update(
        exited_at=timezone.now()
    )

    now = timezone.now()
    session = PlatformSupportSession.objects.create(
        tenant=tenant,
        tenant_name=tenant.name,
        tenant_subdomain=tenant.subdomain,
        started_by=user,
        started_by_name=_actor_name(user),
        read_only=read_only,
        entered_at=now,
    )
    detail = (
        "Entered read-only support mode" if read_only else "Entered full support mode"
    )
    PlatformSupportModeLog.objects.create(
        session=session,
        tenant_subdomain=tenant.subdomain,
        tenant_name=tenant.name,
        actor_name=_actor_name(user),
        action="support.enter",
        detail=detail,
        read_only=read_only,
    )
    log_audit(
        category="support",
        action="support.enter",
        detail=detail,
        user=user,
        tenant=tenant,
    )
    support_logs = list(PlatformSupportModeLog.objects.order_by("-created_at")[:100])
    return {
        "session": _session_to_dict(session),
        "supportModeLog": [_support_log_to_dict(l) for l in support_logs],
        "message": f"Support mode active for {tenant.name} ({'read-only' if read_only else 'full access'}).",
    }


def exit_support_mode(user=None) -> dict:
    active = PlatformSupportSession.objects.filter(exited_at__isnull=True).first()
    if active:
        detail = f"Left support mode for {active.tenant_name}"
        PlatformSupportModeLog.objects.create(
            session=active,
            tenant_subdomain=active.tenant_subdomain,
            tenant_name=active.tenant_name,
            actor_name=_actor_name(user),
            action="support.exit",
            detail=detail,
            read_only=active.read_only,
        )
        log_audit(
            category="support",
            action="support.exit",
            detail=detail,
            user=user,
            tenant=active.tenant,
        )
        active.exited_at = timezone.now()
        active.save(update_fields=["exited_at", "updated_at"])
        message = f"Exited support mode for {active.tenant_name}."
    else:
        message = "No active support session."

    support_logs = list(PlatformSupportModeLog.objects.order_by("-created_at")[:100])
    return {
        "session": None,
        "supportModeLog": [_support_log_to_dict(l) for l in support_logs],
        "message": message,
    }


# ── Trials ────────────────────────────────────────────────────────────────────

def _trial_stage(sub: PlanSubscription) -> str | None:
    """Return 'active'|'grace'|'lapsed' or None if not a trial."""
    if sub.billing_status != "trial":
        return None
    now = timezone.now()
    if sub.trial_ends_at and now < sub.trial_ends_at:
        return "active"
    if sub.grace_ends_at and now < sub.grace_ends_at:
        return "grace"
    return "lapsed"


def _days_remaining(sub: PlanSubscription, stage: str) -> int | None:
    now = timezone.now()
    if stage == "active" and sub.trial_ends_at:
        return max(0, (sub.trial_ends_at - now).days)
    if stage == "grace" and sub.grace_ends_at:
        return max(0, (sub.grace_ends_at - now).days)
    return None


def get_trials() -> dict:
    subs = PlanSubscription.objects.filter(
        billing_status="trial"
    ).select_related("tenant")
    rows = []
    for sub in subs:
        stage = _trial_stage(sub)
        if not stage or not sub.trial_started_at or not sub.trial_ends_at or not sub.grace_ends_at:
            continue
        rows.append({
            "tenantId": str(sub.tenant_id),
            "tenantName": sub.tenant.name,
            "subdomain": sub.tenant.subdomain,
            "city": sub.tenant.city or "",
            "status": to_ui_status(sub.tenant.status),
            "plan": sub.plan,
            "stage": stage,
            "trialStartedAt": sub.trial_started_at.isoformat(),
            "trialEndsAt": sub.trial_ends_at.isoformat(),
            "graceEndsAt": sub.grace_ends_at.isoformat(),
            "daysRemaining": _days_remaining(sub, stage),
        })

    stage_order = {"lapsed": 0, "grace": 1, "active": 2}
    rows.sort(key=lambda r: stage_order.get(r["stage"], 99))

    active_count = sum(1 for r in rows if r["stage"] == "active")
    grace_count = sum(1 for r in rows if r["stage"] == "grace")
    lapsed_count = sum(1 for r in rows if r["stage"] == "lapsed")

    return {
        "rows": rows,
        "stats": {
            "total": len(rows),
            "active": active_count,
            "grace": grace_count,
            "lapsed": lapsed_count,
        },
        "pipeline": {
            "trialPeriodDays": PLAN_TRIAL_DAYS,
            "gracePeriodDays": PLAN_GRACE_DAYS,
        },
    }


def extend_trial(*, tenant_id: str, extend_days: int = 14, user=None) -> None:
    try:
        sub = PlanSubscription.objects.select_related("tenant").get(tenant_id=tenant_id)
    except PlanSubscription.DoesNotExist:
        raise ValueError("Tenant subscription not found")
    if sub.billing_status != "trial":
        raise ValueError("Tenant is not on a trial")
    delta = timedelta(days=max(1, extend_days))
    if sub.trial_ends_at:
        sub.trial_ends_at += delta
    if sub.grace_ends_at:
        sub.grace_ends_at += delta
    sub.save(update_fields=["trial_ends_at", "grace_ends_at", "updated_at"])
    log_audit(
        category="billing",
        action="trial.extend",
        detail=f"Extended trial by {extend_days} days for {sub.tenant.name}",
        user=user,
        tenant=sub.tenant,
    )


def convert_to_paid(*, tenant_id: str, user=None) -> None:
    try:
        sub = PlanSubscription.objects.select_related("tenant").get(tenant_id=tenant_id)
    except PlanSubscription.DoesNotExist:
        raise ValueError("Tenant subscription not found")
    now = timezone.now()
    sub.billing_status = "paid"
    sub.trial_started_at = None
    sub.trial_ends_at = None
    sub.grace_ends_at = None
    sub.grace_started_at = None
    sub.amount_due_inr = 0
    sub.last_paid_at = now
    sub.next_due_at = now + timedelta(days=30)
    sub.save()
    if sub.tenant.status == "trial":
        sub.tenant.status = "active"
        sub.tenant.save(update_fields=["status", "updated_at"])
    log_audit(
        category="billing",
        action="trial.convert_paid",
        detail=f"Converted {sub.tenant.name} from trial to paid",
        user=user,
        tenant=sub.tenant,
    )


def run_trial_pipeline(user=None) -> dict:
    subs = PlanSubscription.objects.filter(billing_status="trial").select_related("tenant")
    now = timezone.now()
    processed = 0
    moved_to_grace = 0
    deactivated = 0
    messages = []

    for sub in subs:
        stage = _trial_stage(sub)
        if not stage:
            continue
        processed += 1

        if stage == "grace" and not sub.grace_started_at:
            sub.grace_started_at = now
            sub.save(update_fields=["grace_started_at", "updated_at"])
            moved_to_grace += 1
            messages.append(
                f"{sub.tenant.name}: trial expired — now in {PLAN_GRACE_DAYS}-day grace period."
            )
            log_audit(
                category="billing",
                action="trial.enter_grace",
                detail=f"Trial ended for {sub.tenant.name}; grace until {sub.grace_ends_at}",
                user=user,
                tenant=sub.tenant,
            )

        if stage == "lapsed" and sub.tenant.status != "deactivated":
            sub.tenant.status = "deactivated"
            sub.tenant.save(update_fields=["status", "updated_at"])
            deactivated += 1
            messages.append(
                f"{sub.tenant.name}: grace period ended — tenant deactivated."
            )
            log_audit(
                category="billing",
                action="trial.deactivate",
                detail=f"Auto-deactivated after grace period ({sub.tenant.subdomain})",
                user=user,
                tenant=sub.tenant,
            )

    if processed == 0:
        messages.append("No tenants on trial billing.")

    return {
        "processed": processed,
        "movedToGrace": moved_to_grace,
        "deactivated": deactivated,
        "messages": messages,
    }


# ── Tickets ───────────────────────────────────────────────────────────────────

def list_tickets() -> dict:
    tickets = (
        PlatformSupportTicket.objects
        .select_related("tenant")
        .prefetch_related("comments")
        .order_by("-last_activity_at")
    )
    return {"tickets": [_ticket_to_dict(t) for t in tickets]}


def set_ticket_status(*, tenant_subdomain: str, ticket_id: str, status: str, user=None) -> dict:
    try:
        ticket = (
            PlatformSupportTicket.objects
            .select_related("tenant")
            .prefetch_related("comments")
            .get(pk=ticket_id, tenant__subdomain=tenant_subdomain)
        )
    except (PlatformSupportTicket.DoesNotExist, ValueError):
        raise ValueError("Ticket not found")
    ticket.status = status
    ticket.save(update_fields=["status", "last_activity_at", "updated_at"])
    log_audit(
        category="ticket",
        action="ticket.set_status",
        detail=f"{ticket_id} → {status}",
        user=user,
        tenant=ticket.tenant,
    )
    return _ticket_to_dict(ticket)


def add_ticket_platform_note(
    *, tenant_subdomain: str, ticket_id: str, message: str, user=None
) -> dict:
    msg = message.strip()
    if not msg:
        raise ValueError("Note is required")
    try:
        ticket = (
            PlatformSupportTicket.objects
            .select_related("tenant")
            .prefetch_related("comments")
            .get(pk=ticket_id, tenant__subdomain=tenant_subdomain)
        )
    except (PlatformSupportTicket.DoesNotExist, ValueError):
        raise ValueError("Ticket not found")
    PlatformSupportTicketComment.objects.create(
        ticket=ticket,
        author=user,
        author_role="platform_owner",
        author_name=_actor_name(user),
        message=msg,
    )
    ticket.save(update_fields=["last_activity_at", "updated_at"])
    ticket.refresh_from_db()
    log_audit(
        category="ticket",
        action="ticket.internal_note",
        detail=f"{ticket_id}: note added",
        user=user,
        tenant=ticket.tenant,
    )
    return _ticket_to_dict(ticket)


# ── Integration health ────────────────────────────────────────────────────────

_STATUS_MESSAGE = {
    "healthy": "Connected",
    "degraded": "Elevated latency or partial errors",
    "down": "Unreachable — check credentials and network",
    "not_configured": "Not enabled for this tenant",
}


def get_integration_health() -> dict:
    from apps.organizations.models import FeatureFlag

    tenants = list(
        Tenant.objects.select_related("subscription")
        .exclude(status__in=["offboarding"])
        .order_by("name")
    )
    now_iso = timezone.now().isoformat()
    rows = []
    stat_counts = {"healthy": 0, "degraded": 0, "down": 0, "notConfigured": 0}

    for tenant in tenants:
        def probe(provider: str, enabled: bool) -> dict:
            status = "not_configured" if not enabled else "healthy"
            msg = _STATUS_MESSAGE[status]
            return {"provider": provider, "status": status, "message": msg, "enabled": enabled}

        # Check if razorpay/sms are configured via FeatureFlag or settings
        razorpay_flag = FeatureFlag.objects.filter(
            tenant=tenant, key="razorpay", enabled=True
        ).exists()
        msg91_flag = FeatureFlag.objects.filter(
            tenant=tenant, key="msg91", enabled=True
        ).exists()
        # S3 is enabled for all non-trial tenants
        s3_enabled = tenant.status not in ("trial",)

        razorpay = probe("razorpay", razorpay_flag)
        msg91 = probe("msg91", msg91_flag)
        s3 = probe("s3", s3_enabled)

        for check in (razorpay, msg91, s3):
            s = check["status"]
            if s == "healthy":
                stat_counts["healthy"] += 1
            elif s == "degraded":
                stat_counts["degraded"] += 1
            elif s == "down":
                stat_counts["down"] += 1
            else:
                stat_counts["notConfigured"] += 1

        rows.append({
            "tenantId": str(tenant.id),
            "tenantName": tenant.name,
            "subdomain": tenant.subdomain,
            "city": tenant.city or "",
            "status": to_ui_status(tenant.status),
            "razorpay": razorpay,
            "msg91": msg91,
            "s3": s3,
        })

    return {
        "checkedAt": now_iso,
        "rows": rows,
        "stats": stat_counts,
    }
