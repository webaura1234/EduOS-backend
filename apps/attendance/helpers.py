"""Pure helpers for attendance — % math, late-mark detection, date bounds.

No DB access here; these operate on values fed by the queries layer.
"""

import calendar
import datetime
import math

LATE_MARK_GRACE_HOURS = 2  # F-108 / EC-ATT-02
_EARTH_RADIUS_M = 6_371_000


def haversine_metres(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance between two lat/lng points, in metres."""
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlmb = math.radians(float(lng2) - float(lng1))
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return _EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_outside_geofence(branch, lat, lng) -> bool:
    """
    True if a mark at (lat, lng) is outside the branch geo-fence.

    Returns False (i.e. allowed) when the branch has no geo-fence configured, or
    when no coordinates were supplied — store-only in those cases.
    """
    if branch.latitude is None or branch.longitude is None or not branch.geofence_radius_m:
        return False
    if lat is None or lng is None:
        return False
    return haversine_metres(branch.latitude, branch.longitude, lat, lng) > branch.geofence_radius_m


def attendance_percent(present_like: int, excused: int, total: int) -> float:
    """
    % = present_like / (total - excused) * 100.

    Excused/leave sessions are removed from the denominator. Returns 0.0 when
    there are no countable sessions.
    """
    denominator = total - excused
    if denominator <= 0:
        return 0.0
    return round(present_like / denominator * 100, 2)


def is_below_threshold(percent: float, threshold: int) -> bool:
    return percent < threshold


def is_late_mark(session_date: datetime.date, slot_end_time: datetime.time,
                 marked_at: datetime.datetime) -> bool:
    """True if marked more than the grace window after the slot ended (F-108)."""
    slot_end = datetime.datetime.combine(session_date, slot_end_time)
    if marked_at.tzinfo is not None:
        marked_at = marked_at.replace(tzinfo=None)
    cutoff = slot_end + datetime.timedelta(hours=LATE_MARK_GRACE_HOURS)
    return marked_at > cutoff


def month_bounds(year: int, month: int) -> tuple[datetime.date, datetime.date]:
    last_day = calendar.monthrange(year, month)[1]
    return datetime.date(year, month, 1), datetime.date(year, month, last_day)
