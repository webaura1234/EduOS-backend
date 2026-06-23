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
