"""Staff attendance reads/writes + working-day computation for monthly summaries."""

import calendar
import datetime

from django.utils import timezone

from apps.academics.queries import holiday as holiday_q
from apps.hr.models import StaffAttendance


def check_in(branch, user, *, on_date=None, status="present"):
    """Mark a staff member present (or given status) for a day. Idempotent per day."""
    on_date = on_date or datetime.date.today()
    obj, _ = StaffAttendance.objects.update_or_create(
        user=user, date=on_date,
        defaults=dict(branch=branch, status=status, marked_at=timezone.now(),
                      created_by=user, updated_by=user),
    )
    return obj


def is_marked(user_id, on_date) -> bool:
    return StaffAttendance.objects.filter(user_id=user_id, date=on_date, is_active=True).exists()


def present_days_in_month(user_id, year, month) -> int:
    return StaffAttendance.objects.filter(
        user_id=user_id, date__year=year, date__month=month,
        status__in=["present", "leave"], is_active=True,
    ).count()


def status_map_for_range(user_id, from_date, to_date) -> dict:
    """Map date → staff attendance status for a user in [from_date, to_date]."""
    rows = StaffAttendance.objects.filter(
        user_id=user_id,
        date__gte=from_date,
        date__lte=to_date,
        is_active=True,
    ).values("date", "status")
    return {r["date"]: r["status"] for r in rows}


def month_attendance_summary(user_id, branch, year, month) -> dict:
    """Present / absent / leave counts and percentage for a calendar month."""
    days_in_month = calendar.monthrange(year, month)[1]
    first = datetime.date(year, month, 1)
    last = datetime.date(year, month, days_in_month)
    status_map = status_map_for_range(user_id, first, last)

    present = absent = leave = 0
    for day in range(1, days_in_month + 1):
        d = datetime.date(year, month, day)
        st = status_map.get(d)
        if st == "present":
            present += 1
        elif st == "absent":
            absent += 1
        elif st == "leave":
            leave += 1

    total_marked = present + absent + leave
    percent = round(present / total_marked * 100) if total_marked else 0
    return {
        "presentDays": present,
        "absentDays": absent,
        "leaveDays": leave,
        "attendancePercent": percent,
    }


def working_days_in_month(branch, year, month) -> int:
    """Count working days in a month: weekdays in branch.working_days, minus holidays.

    branch.working_days uses 0=Sun..6=Sat (matches date.isoweekday() % 7).
    """
    working = set(branch.working_days or [1, 2, 3, 4, 5, 6])
    days_in_month = calendar.monthrange(year, month)[1]
    first = datetime.date(year, month, 1)
    last = datetime.date(year, month, days_in_month)

    holiday_dates = {
        h.date for h in holiday_q.list_holidays(branch.pk, from_date=first, to_date=last)
    }
    count = 0
    for day in range(1, days_in_month + 1):
        d = datetime.date(year, month, day)
        if (d.isoweekday() % 7) in working and d not in holiday_dates:
            count += 1
    return count
