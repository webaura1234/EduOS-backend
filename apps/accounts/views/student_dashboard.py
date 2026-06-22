"""Student dashboard — composes attendance, fees, schedule, and exams for the home page."""

import datetime

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsStudent
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.attendance.interactors import report as report_i
from apps.communications.queries import announcement as ann_q
from apps.communications.views.announcement import _announcement
from apps.examinations.interactors import hub as exam_hub_i
from apps.fees.queries.invoice import list_dues_for_student_user

_DAY_LABELS = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday",
               5: "Friday", 6: "Saturday", 7: "Sunday"}


def _schedule_today(branch, batch_id) -> list:
    weekday = datetime.date.today().isoweekday()  # Mon=1..Sun=7 (matches DayOfWeek)
    items = []
    for e in tt_q.list_active_entries_for_branch(branch.pk):
        if e.timetable.batch_id != batch_id or e.day_of_week != weekday:
            continue
        slot = e.period_slot
        subject = e.batch_subject.subject if e.batch_subject_id else None
        items.append({
            "subjectName": subject.name if subject else "Subject",
            "startTime": slot.start_time.isoformat() if slot else "",
            "endTime": slot.end_time.isoformat() if slot else "",
            "roomName": e.room.name if e.room_id else "—",
            "dayLabel": _DAY_LABELS.get(weekday, "Today"),
        })
    return items


def _attendance_alert(pct, threshold):
    if pct < threshold:
        return {
            "level": "critical",
            "message": f"Attendance is {pct}% — below the required {threshold}%. "
                       "You may be barred from exams.",
            "attendancePercent": pct, "thresholdPercent": threshold,
        }
    if pct < threshold + 5:
        return {
            "level": "warning",
            "message": f"Attendance is {pct}% — close to the {threshold}% requirement.",
            "attendancePercent": pct, "thresholdPercent": threshold,
        }
    return None


class StudentDashboardView(APIView):
    """GET → StudentDashboardData for the logged-in student."""
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        tenant = branch.tenant
        user = request.user
        profile = getattr(user, "student_profile", None)
        enrollment = get_active_enrollment_for_profile(profile.pk) if profile else None

        # Profile block
        batch = enrollment.batch if enrollment else None
        profile_block = {
            "studentId": str(profile.id) if profile else str(user.id),
            "name": user.full_name,
            "classLabel": batch.name if batch else "",
            "classSectionId": str(batch.id) if batch else "",
            "rollNumber": user.custom_login_id,
        }

        # Each section degrades to a safe default so one failure can't break the page.
        # Attendance
        attendance_pct, threshold = 0, 75
        try:
            if enrollment:
                summary = report_i.student_summary(branch, enrollment)
                attendance_pct = summary["overallPercent"]
                threshold = summary["threshold"]
        except Exception:
            pass

        # Fees
        fee_alert = None
        try:
            open_paise = sum(inv.balance_paise for inv in list_dues_for_student_user(user.id))
            if open_paise > 0:
                rupees = round(open_paise / 100, 2)
                fee_alert = {"message": f"Fee balance due: ₹{rupees:,.0f}", "amountDue": rupees}
        except Exception:
            pass

        # Exams (composes the existing exam hub)
        upcoming, next_label, hall_ticket = [], None, False
        if profile:
            try:
                hub = exam_hub_i.build_exam_hub(profile, tenant=tenant)
                upcoming = hub.get("upcomingExams", [])
                hall_ticket = bool(hub.get("hallTicketAvailable", False))
                if upcoming:
                    first = upcoming[0]
                    next_label = first.get("examName") or first.get("subjectName") or first.get("title")
            except Exception:
                pass

        # Schedule
        try:
            schedule = _schedule_today(branch, batch.id) if batch else []
        except Exception:
            schedule = []

        # Announcements
        try:
            announcements = [
                _announcement(a)
                for a in ann_q.list_for_student(
                    branch.pk, batch_id=(batch.id if batch else None),
                )[:4]
            ]
        except Exception:
            announcements = []

        return Response({
            "institutionType": tenant.institution_type,
            "profile": profile_block,
            "attendancePercent": attendance_pct,
            "attendanceThreshold": threshold,
            "attendanceAlert": _attendance_alert(attendance_pct, threshold),
            "feeAlert": fee_alert,
            "scheduleToday": schedule,
            "upcomingExamsCount": len(upcoming),
            "nextExamLabel": next_label,
            "hallTicketAvailable": hall_ticket,
            "announcements": announcements,
        })
