"""Faculty timetable — weekly teaching schedule + personal attendance calendar."""

import calendar
import datetime

from apps.academics.helpers import batch_display_label
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import holiday as hol_q
from apps.academics.queries import timetable as tt_q
from apps.hr.queries import employee as emp_q
from apps.hr.queries import leave as leave_q
from apps.hr.queries import staff_attendance as sa_q


def _period(entry) -> dict:
    slot = entry.period_slot
    subject = entry.batch_subject.subject if entry.batch_subject_id else None
    batch = entry.timetable.batch
    return {
        "entryId": str(entry.id),
        "classSectionId": str(batch.pk),
        "classLabel": batch_display_label(batch),
        "subjectId": str(subject.id) if subject else "",
        "subjectName": subject.name if subject else "Subject",
        "roomId": str(entry.room_id) if entry.room_id else "",
        "roomName": entry.room.name if entry.room_id else "—",
        "startTime": slot.start_time.isoformat() if slot else "",
        "endTime": slot.end_time.isoformat() if slot else "",
        "periodIndex": slot.sequence if slot else 0,
    }


def _weekly(entries) -> dict:
    by_day: dict = {}
    for e in entries:
        by_day.setdefault(e.day_of_week, []).append(e)
    days = []
    for day in sorted(by_day.keys()):
        periods = sorted(
            by_day[day],
            key=lambda x: (x.period_slot.sequence if x.period_slot_id else 0),
        )
        days.append({
            "dayOfWeek": day,
            "label": DayOfWeek(day).label,
            "periods": [_period(e) for e in periods],
        })
    return {"days": days}


def _is_working_day(branch, d: datetime.date) -> bool:
    working = set(branch.working_days or [1, 2, 3, 4, 5, 6])
    return (d.isoweekday() % 7) in working


def _day_kind(*, on_date, branch, holiday_by_date, leave_by_date) -> str:
    if holiday_by_date.get(on_date):
        return "holiday"
    if leave_by_date.get(on_date):
        return "leave"
    if not _is_working_day(branch, on_date):
        return "off"
    return "working"


def _staff_display_status(*, on_date, day_kind, raw_status, today) -> str:
    if day_kind == "holiday":
        return "holiday"
    if day_kind == "leave":
        return "leave"
    if day_kind == "off":
        return "off"
    if raw_status in ("present", "absent", "leave"):
        return raw_status
    if on_date > today:
        return "not_due"
    return "not_marked"


def build_faculty_timetable(*, branch, user, year: int, month: int, detail_date=None) -> dict:
    today = datetime.date.today()
    faculty_id = user.pk
    branch_id = branch.pk

    entries = list(tt_q.list_faculty_teaching_slots(branch_id, faculty_id))
    weekly = _weekly(entries)

    days_in_month = calendar.monthrange(year, month)[1]
    first = datetime.date(year, month, 1)
    last = datetime.date(year, month, days_in_month)

    holidays_qs = list(hol_q.list_holidays(branch_id, from_date=first, to_date=last))
    holiday_by_date = {h.date: h for h in holidays_qs}

    emp = emp_q.get_employee_for_user(faculty_id)
    leave_by_date = leave_q.approved_leave_dates(emp.pk, first, last) if emp else {}
    staff_status_map = sa_q.status_map_for_range(faculty_id, first, last)

    current_year = cal_q.get_current_year(branch_id)
    vacation_periods = []
    if current_year:
        for p in cal_q.list_periods(current_year.pk):
            vacation_periods.append({
                "id": str(p.pk),
                "name": p.name,
                "startDate": p.start_date.isoformat(),
                "endDate": p.end_date.isoformat(),
            })

    calendar_days = []
    for day_num in range(1, days_in_month + 1):
        on_date = datetime.date(year, month, day_num)
        holiday = holiday_by_date.get(on_date)
        leave_reason = leave_by_date.get(on_date)
        day_kind = _day_kind(
            on_date=on_date,
            branch=branch,
            holiday_by_date=holiday_by_date,
            leave_by_date=leave_by_date,
        )
        raw = staff_status_map.get(on_date)
        calendar_days.append({
            "date": on_date.isoformat(),
            "dayKind": day_kind,
            "holidayName": holiday.name if holiday else None,
            "holidayType": holiday.holiday_type if holiday else None,
            "leaveReason": leave_reason,
            "staffStatus": raw if day_kind == "working" else None,
        })

    summary = sa_q.month_attendance_summary(faculty_id, branch, year, month)
    summary["monthLabel"] = first.strftime("%B %Y")

    holidays_payload = [
        {
            "id": str(h.pk),
            "name": h.name,
            "date": h.date.isoformat(),
            "holidayType": h.holiday_type,
        }
        for h in holidays_qs
    ]

    payload = {
        "weekly": weekly,
        "calendar": {
            "year": year,
            "month": month,
            "days": calendar_days,
            "holidays": holidays_payload,
            "vacationPeriods": vacation_periods,
        },
        "summary": summary,
    }

    if detail_date:
        on_date = detail_date
        holiday = holiday_by_date.get(on_date)
        leave_reason = leave_by_date.get(on_date)
        day_kind = _day_kind(
            on_date=on_date,
            branch=branch,
            holiday_by_date=holiday_by_date,
            leave_by_date=leave_by_date,
        )
        raw = staff_status_map.get(on_date)
        display = _staff_display_status(
            on_date=on_date, day_kind=day_kind, raw_status=raw, today=today,
        )
        payload["dayDetail"] = {
            "date": on_date.isoformat(),
            "dayKind": day_kind,
            "leaveReason": leave_reason,
            "holidayName": holiday.name if holiday else None,
            "staffStatus": display,
            "canCheckIn": on_date == today and display == "not_marked",
        }

    return payload
