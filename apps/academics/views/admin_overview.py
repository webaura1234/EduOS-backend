"""Admin Academics overview — the AcademicsData aggregate the admin screen consumes.

Real data for every domain the backend models (years, periods, holidays, departments,
class sections, subjects, rooms, timetable, faculty). Domains not yet modelled
(substitutions, study materials, admin review queue, calendar-change log) return
empty lists, and working days return a sensible default, so the screen renders fully.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import admin_extras as extra_q
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import holiday as hol_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.accounts.models.user import Role, User
from apps.accounts.permissions import IsAdminOrSuperAdmin

_TBD_SUBJECT = "__tbd__"
_UNASSIGNED_FACULTY = "__unassigned__"

_DAY_LABELS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _working_days(branch) -> list:
    working = set(branch.working_days or [])
    return [
        {"dayOfWeek": d, "label": _DAY_LABELS[d], "isWorkingDay": d in working}
        for d in range(7)
    ]


def _substitution(s) -> dict:
    return {
        "id": str(s.id),
        "timetableSlotId": str(s.timetable_entry_id),
        "originalFacultyUserId": str(s.original_faculty_id) if s.original_faculty_id else "",
        "substituteFacultyUserId": str(s.substitute_faculty_id),
        "date": s.date.isoformat(),
        "reason": s.reason,
        "status": s.status,
        "createdAt": s.created_at.isoformat(),
    }


def _study_material(m) -> dict:
    label = ""
    if m.batch_id:
        label = (f"{m.batch.course.name} - {m.batch.name}"
                 if m.batch.course_id else m.batch.name)
    return {
        "id": str(m.id),
        "classSectionId": str(m.batch_id) if m.batch_id else "",
        "classLabel": label,
        "fileName": m.file_name,
        "s3Key": m.s3_key,
        "url": m.url,
        "uploadedAt": m.created_at.isoformat(),
        "uploadedByUserId": str(m.uploaded_by_id) if m.uploaded_by_id else "",
    }


def _calendar_change(c) -> dict:
    return {
        "id": str(c.id),
        "changeType": c.change_type,
        "description": c.description,
        "effectiveDate": c.effective_date.isoformat(),
        "attendanceFrozenThrough": c.attendance_frozen_through.isoformat()
        if c.attendance_frozen_through else "",
        "createdAt": c.created_at.isoformat(),
    }


def _review_queue(branch_id) -> list:
    tbd_ids, unassigned_ids = extra_q.review_entries(branch_id)
    items = []
    if tbd_ids:
        items.append({
            "id": "review-tbd",
            "type": "tbd_slots",
            "message": f"{len(tbd_ids)} timetable slot(s) need a subject reassigned.",
            "slotIds": tbd_ids,
            "createdAt": "",
            "resolved": False,
        })
    if unassigned_ids:
        items.append({
            "id": "review-faculty",
            "type": "faculty_unassigned",
            "message": f"{len(unassigned_ids)} timetable slot(s) need a faculty assigned.",
            "slotIds": unassigned_ids,
            "createdAt": "",
            "resolved": False,
        })
    return items


def _period(p) -> dict:
    return {
        "id": str(p.id),
        "kind": p.period_type,  # "term" | "semester" — matches CalendarPeriodKind
        "label": p.name,
        "startDate": p.start_date.isoformat(),
        "endDate": p.end_date.isoformat(),
        "academicYearId": str(p.academic_year_id),
    }


def _subject(s) -> dict:
    return {
        "id": str(s.id),
        "code": s.code,
        "name": s.name,
        "syllabusUnits": [],          # syllabus units not modelled yet
        "credits": s.credits,
        "archived": not s.is_active,
        "hasMarks": False,            # avoid an N+1 marks probe per subject
        "syllabusCompletionPercent": 0,
        "completedUnitIds": [],
    }


def _class_section(b) -> dict:
    return {
        "id": str(b.id),
        "label": b.name,
        "departmentId": str(b.course.department_id),
        "batch": b.name,
        "section": None,
    }


def _timetable_slot(e) -> dict:
    slot = e.period_slot
    has_faculty = e.faculty_id is not None
    return {
        "id": str(e.id),
        "classSectionId": str(e.timetable.batch_id),
        "subjectId": str(e.batch_subject.subject_id) if e.batch_subject_id else _TBD_SUBJECT,
        "facultyUserId": str(e.faculty_id) if has_faculty else _UNASSIGNED_FACULTY,
        "roomId": str(e.room_id) if e.room_id else "",
        "dayOfWeek": e.day_of_week,
        "periodIndex": slot.sequence if slot else 0,
        "startTime": slot.start_time.isoformat() if slot else "",
        "endTime": slot.end_time.isoformat() if slot else "",
        "status": "active" if has_faculty else "faculty_unassigned",
        "statusNote": None,
    }


class AdminAcademicsOverviewView(APIView):
    """GET → AcademicsData (full academics aggregate for the admin screen)."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        tenant = branch.tenant
        is_college = tenant.institution_type == "college"

        years = list(cal_q.list_years(branch.pk))
        current_year = cal_q.get_current_year(branch.pk)
        periods = list(cal_q.list_periods(current_year.pk)) if current_year else []

        faculty = [
            {"userId": str(u.id), "name": u.full_name}
            for u in User.objects.filter(
                tenant_id=tenant.id, branch_id=branch.pk,
                role=Role.FACULTY, is_active=True,
            ).order_by("first_name", "last_name")
        ]

        return Response({
            "institutionType": tenant.institution_type,
            # College uses "Department" hierarchy; school uses "Stream".
            "hierarchyLabel": "Department" if is_college else "Stream",
            "periodKind": "semester" if is_college else "term",
            "academicYears": [{"id": str(y.id), "label": y.name} for y in years],
            "periods": [_period(p) for p in periods],
            "holidays": [
                {"id": str(h.id), "name": h.name, "date": h.date.isoformat()}
                for h in hol_q.list_holidays(branch.pk)
            ],
            "workingDays": _working_days(branch),
            "departments": [
                {"id": str(d.id), "name": d.name,
                 "parentId": str(d.parent_id) if d.parent_id else None}
                for d in struct_q.list_departments(branch.pk)
            ],
            "classSections": [_class_section(b) for b in struct_q.list_batches(branch.pk)],
            "subjects": [_subject(s) for s in curr_q.list_subjects(branch.pk)],
            "rooms": [
                {"id": str(r.id), "name": r.name} for r in tt_q.list_rooms(branch.pk)
            ],
            "timetableSlots": [
                _timetable_slot(e) for e in tt_q.list_active_entries_for_branch(branch.pk)
            ],
            "faculty": faculty,
            "substitutions": [
                _substitution(s) for s in extra_q.list_substitutions(branch.pk)
            ],
            "studyMaterials": [
                _study_material(m) for m in extra_q.list_study_materials(branch.pk)
            ],
            "adminReviewQueue": _review_queue(branch.pk),
            "calendarChanges": [
                _calendar_change(c) for c in extra_q.list_calendar_changes(branch.pk)
            ],
            "attendanceFrozenThrough": (
                frozen.isoformat()
                if (frozen := extra_q.latest_frozen_through(branch.pk)) else None
            ),
        })
