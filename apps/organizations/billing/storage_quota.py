"""
Tenant storage quota — Pii Aura policy.

Included storage = licensed_students × STORAGE_MB_PER_LICENSED_STUDENT.
Gallery WebP + thumbnails count toward usage. Staging/CSV exports do not.
storage_limit_gb == 0 means no allowance (block uploads), not unlimited.
"""

from __future__ import annotations

import datetime
import math
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import F, Sum
from rest_framework.exceptions import ValidationError

from apps.organizations.enums import QuotaPeriod, QuotaResource
from apps.organizations.models import PlanSubscription, TenantQuota

# Sentinel period_start for lifetime (total) storage counters.
STORAGE_PERIOD_START = datetime.date(1970, 1, 1)


def mb_per_licensed_student() -> int:
    return int(getattr(settings, "STORAGE_MB_PER_LICENSED_STUDENT", 100))


def warn_percent() -> int:
    return int(getattr(settings, "STORAGE_WARN_PERCENT", 80))


def critical_percent() -> int:
    return int(getattr(settings, "STORAGE_CRITICAL_PERCENT", 90))


def storage_limit_gb_for_licenses(licensed_students: int) -> int:
    """Included GB = ceil(licensed_students × MB / 1000) for marketing GB (100→10, 500→50)."""
    n = max(int(licensed_students or 0), 0)
    if n <= 0:
        return 0
    return math.ceil(n * mb_per_licensed_student() / 1000)


def limit_bytes_from_gb(storage_limit_gb: int) -> int:
    return max(int(storage_limit_gb or 0), 0) * 1024 * 1024 * 1024


def licensed_student_count(tenant) -> int:
    """Purchased license seats (paid capacity). Falls back to consumed."""
    from apps.organizations.models import TenantLicenseSummary

    summary = TenantLicenseSummary.objects.filter(tenant=tenant).first()
    if summary is None:
        return 0
    return max(summary.licenses_purchased or 0, summary.licenses_consumed or 0)


def sync_storage_limit_for_tenant(tenant) -> int:
    """Derive PlanSubscription.storage_limit_gb from licensed seats; sync quota caps."""
    limit_gb = storage_limit_gb_for_licenses(licensed_student_count(tenant))
    PlanSubscription.objects.filter(tenant=tenant).update(storage_limit_gb=limit_gb)
    quota = get_or_create_storage_quota(tenant)
    hard = limit_bytes_from_gb(limit_gb)
    soft = int(hard * warn_percent() / 100) if hard > 0 else 0
    if quota.hard_cap != hard or quota.soft_cap != soft:
        quota.hard_cap = hard
        quota.soft_cap = soft
        quota.save(update_fields=["hard_cap", "soft_cap", "updated_at"])
    return limit_gb


def get_or_create_storage_quota(tenant) -> TenantQuota:
    sub = PlanSubscription.objects.filter(tenant=tenant).first()
    limit_gb = sub.storage_limit_gb if sub else 0
    hard = limit_bytes_from_gb(limit_gb)
    soft = int(hard * warn_percent() / 100) if hard > 0 else 0
    quota, created = TenantQuota.objects.get_or_create(
        tenant=tenant,
        resource=QuotaResource.STORAGE_BYTES,
        period_start=STORAGE_PERIOD_START,
        defaults={
            "period": QuotaPeriod.TOTAL,
            "usage": 0,
            "soft_cap": soft,
            "hard_cap": hard,
        },
    )
    if not created and quota.period != QuotaPeriod.TOTAL:
        quota.period = QuotaPeriod.TOTAL
        quota.save(update_fields=["period", "updated_at"])
    return quota


def get_usage_bytes(tenant) -> int:
    return int(get_or_create_storage_quota(tenant).usage or 0)


def get_limit_bytes(tenant) -> int:
    sub = PlanSubscription.objects.filter(tenant=tenant).first()
    if sub is None:
        return 0
    return limit_bytes_from_gb(sub.storage_limit_gb)


@transaction.atomic
def adjust_storage_usage(tenant, delta_bytes: int) -> TenantQuota:
    """Increment or decrement STORAGE_BYTES usage (never below zero)."""
    if not delta_bytes:
        return get_or_create_storage_quota(tenant)
    quota = (
        TenantQuota.objects.select_for_update()
        .filter(
            tenant=tenant,
            resource=QuotaResource.STORAGE_BYTES,
            period_start=STORAGE_PERIOD_START,
        )
        .first()
    )
    if quota is None:
        quota = get_or_create_storage_quota(tenant)
        quota = TenantQuota.objects.select_for_update().get(pk=quota.pk)
    if delta_bytes > 0:
        TenantQuota.objects.filter(pk=quota.pk).update(usage=F("usage") + delta_bytes)
    else:
        # Clamp at zero in SQL-ish way after refresh.
        TenantQuota.objects.filter(pk=quota.pk).update(
            usage=F("usage") + delta_bytes,
        )
        TenantQuota.objects.filter(pk=quota.pk, usage__lt=0).update(usage=0)
    quota.refresh_from_db()
    return quota


def assert_can_upload(tenant, estimated_bytes: int) -> None:
    """Reject when current usage + estimate would exceed hard limit."""
    estimate = max(int(estimated_bytes or 0), 0)
    limit = get_limit_bytes(tenant)
    used = get_usage_bytes(tenant)
    # 0 limit = no allowance (block), not uncapped.
    if limit <= 0 or (used + estimate) > limit:
        raise ValidationError({
            "storage": (
                "Storage limit reached. Delete unused gallery media or increase "
                "licensed students to continue uploading."
            ),
            "usedBytes": used,
            "limitBytes": limit,
            "estimatedBytes": estimate,
        })


def warning_level(percent_used: float, *, blocked: bool = False) -> str:
    if blocked or percent_used >= 100:
        return "blocked"
    if percent_used >= critical_percent():
        return "critical"
    if percent_used >= warn_percent():
        return "warn"
    return "none"


def warning_message(level: str) -> str | None:
    if level == "blocked":
        return (
            "Storage limit reached. Delete unused gallery media or increase "
            "licensed students to continue uploading."
        )
    if level == "critical":
        return (
            "Only 10% storage remaining. Consider increasing licensed students "
            "or removing old media."
        )
    if level == "warn":
        return "Storage almost full. You have used 80% of your allocated storage."
    return None


def storage_warning_snapshot(tenant) -> dict[str, Any]:
    """Compact warning fields for embed in upload/list API responses."""
    used = get_usage_bytes(tenant)
    limit = get_limit_bytes(tenant)
    percent = round((used / limit) * 100, 1) if limit > 0 else (100.0 if used > 0 else 0.0)
    blocked = limit <= 0 or used >= limit
    level = warning_level(percent, blocked=blocked)
    return {
        "usedBytes": used,
        "limitBytes": limit,
        "percentUsed": percent,
        "warningLevel": level,
        "message": warning_message(level),
    }


def storage_status_payload(tenant) -> dict[str, Any]:
    """API payload for admin Storage card and gallery warnings."""
    from apps.gallery.models import GalleryAlbum, GalleryImage
    from apps.gallery.enums import ProcessingStatus

    snap = storage_warning_snapshot(tenant)
    used = snap["usedBytes"]

    ready = GalleryImage.objects.filter(
        album__branch__tenant=tenant,
        processing_status=ProcessingStatus.READY,
        is_active=True,
        album__is_active=True,
    )
    total_images = ready.count()
    albums_qs = GalleryAlbum.objects.filter(branch__tenant=tenant, is_active=True)
    album_count = albums_qs.count()
    last_upload = (
        ready.order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    largest = (
        albums_qs.order_by("-total_images")
        .values("id", "title", "total_images")
        .first()
    )

    return {
        **snap,
        "licensedStudents": licensed_student_count(tenant),
        "mbPerStudent": mb_per_licensed_student(),
        "breakdown": {
            "galleryBytes": used,  # v1: only gallery is metered
            "documentsBytes": 0,  # not metered yet
            "exportsBytes": 0,  # excluded / ephemeral
        },
        "stats": {
            "totalImages": total_images,
            "albums": album_count,
            "lastUploadAt": last_upload.isoformat() if last_upload else None,
            "largestAlbum": (
                {
                    "id": str(largest["id"]),
                    "title": largest["title"],
                    "totalImages": largest["total_images"],
                }
                if largest
                else None
            ),
        },
    }


def recompute_gallery_usage(tenant) -> int:
    """Sum stored_bytes for ready gallery images; set TenantQuota.usage."""
    from apps.gallery.enums import ProcessingStatus
    from apps.gallery.models import GalleryImage

    total = (
        GalleryImage.objects.filter(
            album__branch__tenant=tenant,
            processing_status=ProcessingStatus.READY,
            is_active=True,
            album__is_active=True,
        ).aggregate(total=Sum("stored_bytes"))["total"]
        or 0
    )
    quota = get_or_create_storage_quota(tenant)
    quota.usage = int(total)
    quota.save(update_fields=["usage", "updated_at"])
    return int(total)
