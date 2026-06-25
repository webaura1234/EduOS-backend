"""Live attendance board — branch snapshot for admin dashboards (F-101).

Single implementation shared by /admin-overview/live/ and /live/. Aggregates
today's sessions by batch with roster-sized denominators (not marked-count only).
Short-lived cache per branch+date; invalidated when marks change.
"""

import datetime

from django.core.cache import cache
from django.utils import timezone

from apps.academics.helpers import batch_display_label
from apps.attendance.queries import record as record_q
from apps.attendance.queries import roster as roster_q
from apps.attendance.queries import session as session_q

CACHE_TTL_SECONDS = 30


def _cache_key(branch_id, date: datetime.date) -> str:
    return f"attendance:live:{branch_id}:{date.isoformat()}"


def invalidate_live_cache(branch_id, date=None) -> None:
    """Drop cached snapshot after a mark or correction."""
    day = date or datetime.date.today()
    cache.delete(_cache_key(branch_id, day))


def branch_live_snapshot(branch, *, date=None) -> dict:
    """
    LiveAttendanceSnapshot for a branch.

    - present: students marked present or late across today's sessions, per batch
    - total: active roster size per batch (enrolled students)
    - Only batches with at least one session today are listed
    """
    day = date or datetime.date.today()
    key = _cache_key(branch.pk, day)
    cached = cache.get(key)
    if cached is not None:
        return cached

    sessions = list(session_q.list_sessions_for_date(branch.pk, day))
    if not sessions:
        snapshot = {
            "present": 0,
            "total": 0,
            "percent": 0,
            "classes": [],
            "updatedAt": timezone.now().isoformat(),
        }
        cache.set(key, snapshot, CACHE_TTL_SECONDS)
        return snapshot

    session_ids = [s.pk for s in sessions]
    counts_by_session = record_q.status_counts_for_sessions(session_ids)

    present_by_batch: dict[str, int] = {}
    batch_by_id: dict[str, object] = {}
    for session in sessions:
        bid = str(session.batch_id)
        batch_by_id.setdefault(bid, session.batch)
        counts = counts_by_session.get(str(session.pk), {})
        present_by_batch[bid] = present_by_batch.get(bid, 0) + (
            counts.get("present", 0) + counts.get("late", 0)
        )

    batch_ids = list(batch_by_id.keys())
    roster_by_batch = roster_q.roster_counts_for_batches(batch_ids)

    classes = []
    present_total = total_total = 0
    for bid in sorted(batch_ids, key=lambda x: batch_display_label(batch_by_id[x])):
        batch = batch_by_id[bid]
        present = present_by_batch.get(bid, 0)
        total = roster_by_batch.get(bid, 0)
        classes.append({
            "classId": bid,
            "classLabel": batch_display_label(batch),
            "present": present,
            "total": total,
        })
        present_total += present
        total_total += total

    percent = round(present_total / total_total * 100) if total_total else 0
    snapshot = {
        "present": present_total,
        "total": total_total,
        "percent": percent,
        "classes": classes,
        "updatedAt": timezone.now().isoformat(),
    }
    cache.set(key, snapshot, CACHE_TTL_SECONDS)
    return snapshot
