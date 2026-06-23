"""Admin Academics write actions for the gap domains: working days, substitutions,
study materials. (Periods/departments/subjects/timetable/holidays have their own
dedicated endpoints already.)"""

import datetime

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import DepartmentType, SubjectType
from apps.academics.queries import admin_extras as extra_q
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin


def _date(value):
    return datetime.date.fromisoformat(value) if value else datetime.date.today()


def _next_period_sequence(year_id) -> int:
    existing = list(cal_q.list_periods(year_id).values_list("sequence", flat=True))
    return (max(existing) + 1) if existing else 1


_TBD_SUBJECT = "__tbd__"
_UNASSIGNED_FACULTY = "__unassigned__"


def _time(value):
    if not value:
        return None
    try:
        return datetime.time.fromisoformat(value)
    except ValueError:
        h, _, m = value.partition(":")
        return datetime.time(int(h), int(m or 0))


def _resolve_period_slot(branch, period_index, start_time, end_time, user):
    """Find a period slot by sequence, or create one from the slot's index + times."""
    slot = tt_q.list_period_slots(branch.pk).filter(sequence=period_index).first()
    if slot is not None:
        return slot
    return tt_q.create_period_slot(
        branch.pk, name=f"Period {period_index}", sequence=period_index,
        start_time=_time(start_time) or datetime.time(9, 0),
        end_time=_time(end_time) or datetime.time(10, 0), user=user,
    )


def _resolve_batch_subject(branch, batch, subject, period, user):
    existing = (
        curr_q.list_batch_subjects(branch.pk, batch_id=batch.id, academic_period_id=period.id)
        .filter(subject_id=subject.id)
        .first()
    )
    if existing is not None:
        return existing
    return curr_q.create_batch_subject(
        batch=batch, subject=subject, academic_period=period, user=user,
    )


def _resolve_course(branch, department_id, user):
    """Find a course to attach subjects/sections to, creating a default
    department + course when the flat FE shape doesn't supply one."""
    dept = None
    if department_id:
        dept = struct_q.get_department(branch.pk, department_id)
    if dept is None:
        dept = struct_q.list_departments(branch.pk).first()
    if dept is None:
        dept = struct_q.create_department(
            branch.pk, name="General", department_type=DepartmentType.DEPARTMENT, user=user,
        )
    course = struct_q.list_courses(branch.pk, department_id=dept.id).first()
    if course is None:
        course = struct_q.create_course(department=dept, name=dept.name or "General", user=user)
    return course


class AdminAcademicsActionView(APIView):
    """POST { action, ... } → dispatch a gap-domain academics write."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        user = request.user
        action = request.data.get("action")
        payload = request.data.get("payload") or request.data

        if action == "set_working_days":
            rules = request.data.get("rules") or payload.get("rules") or []
            day_numbers = [r["dayOfWeek"] for r in rules if r.get("isWorkingDay")]
            extra_q.set_working_days(branch, day_numbers, user=user)
            extra_q.create_calendar_change(
                branch=branch, change_type="working_days",
                description="Working days updated.", effective_date=datetime.date.today(),
                user=user,
            )
            return Response({"ok": True, "workingDays": branch.working_days})

        if action == "save_period":
            # FE sends {label, startDate, endDate, academicYearId}; derive type + sequence.
            period_type = "semester" if branch.tenant.institution_type == "college" else "term"
            pid = payload.get("id")
            if pid:
                period = cal_q.get_period(payload.get("academicYearId"), pid)
                if period is None:
                    return Response({"error": "Period not found."}, status=status.HTTP_404_NOT_FOUND)
                cal_q.update_period(period, {
                    "name": payload.get("label", period.name),
                    "start_date": _date(payload.get("startDate")),
                    "end_date": _date(payload.get("endDate")),
                }, user=user)
                return Response({"id": str(period.id)})
            period = cal_q.create_period(
                payload.get("academicYearId"),
                period_type=period_type,
                sequence=_next_period_sequence(payload.get("academicYearId")),
                name=payload.get("label", "Term"),
                start_date=_date(payload.get("startDate")),
                end_date=_date(payload.get("endDate")),
                user=user,
            )
            return Response({"id": str(period.id)}, status=status.HTTP_201_CREATED)

        if action == "save_department":
            # FE sends {id?, name, parentId?}; department_type defaults on the model.
            did = payload.get("id")
            parent_id = payload.get("parentId") or None
            if did:
                dept = struct_q.get_department(branch.pk, did)
                if dept is None:
                    return Response({"error": "Department not found."}, status=status.HTTP_404_NOT_FOUND)
                struct_q.update_department(
                    dept, {"name": payload.get("name", dept.name), "parent_id": parent_id}, user=user,
                )
                return Response({"id": str(dept.id)})
            dept = struct_q.create_department(
                branch.pk, name=payload.get("name", "Department"),
                department_type=DepartmentType.DEPARTMENT, user=user,
            )
            if parent_id:
                dept.parent_id = parent_id
                dept.save(update_fields=["parent"])
            return Response({"id": str(dept.id)}, status=status.HTTP_201_CREATED)

        if action == "save_subject":
            # FE sends {id?, code, name, credits?}; resolve a course to attach to.
            sid = payload.get("id")
            if sid:
                subj = curr_q.get_subject(branch.pk, sid)
                if subj is None:
                    return Response({"error": "Subject not found."}, status=status.HTTP_404_NOT_FOUND)
                curr_q.update_subject(subj, {
                    "name": payload.get("name", subj.name),
                    "code": payload.get("code", subj.code),
                    "credits": payload.get("credits"),
                }, user=user)
                return Response({"id": str(subj.id)})
            course = _resolve_course(branch, payload.get("departmentId"), user)
            subj = curr_q.create_subject(
                course=course, name=payload.get("name", "Subject"),
                code=payload.get("code", ""), subject_type=SubjectType.THEORY,
                credits=payload.get("credits"), user=user,
            )
            return Response({"id": str(subj.id)}, status=status.HTTP_201_CREATED)

        if action == "save_class_section":
            name = payload.get("label") or payload.get("name") or "Section"
            sid = payload.get("id")
            if sid:
                batch = struct_q.get_batch(branch.pk, sid)
                if batch is None:
                    return Response({"error": "Class section not found."}, status=status.HTTP_404_NOT_FOUND)
                struct_q.update_batch(batch, {"name": name}, user=user)
                return Response({"id": str(batch.id)})
            year = cal_q.get_current_year(branch.pk)
            if year is None:
                return Response(
                    {"error": "Set a current academic year before creating class sections."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            course = _resolve_course(branch, payload.get("departmentId"), user)
            batch = struct_q.create_batch(
                course=course, academic_year=year, name=name, user=user,
            )
            return Response({"id": str(batch.id)}, status=status.HTTP_201_CREATED)

        if action == "save_timetable_slot":
            batch = struct_q.get_batch(branch.pk, payload.get("classSectionId"))
            if batch is None:
                return Response({"error": "Class section not found."}, status=status.HTTP_404_NOT_FOUND)

            subject_id = payload.get("subjectId")
            if not subject_id or subject_id == _TBD_SUBJECT:
                return Response({"error": "A subject is required for a timetable slot."},
                                status=status.HTTP_400_BAD_REQUEST)
            subject = curr_q.get_subject(branch.pk, subject_id)
            if subject is None:
                return Response({"error": "Subject not found."}, status=status.HTTP_404_NOT_FOUND)

            year = cal_q.get_current_year(branch.pk)
            period = cal_q.list_periods(year.pk).first() if year else None
            if period is None:
                return Response(
                    {"error": "Create a current academic year with at least one term/period first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            faculty_raw = payload.get("facultyUserId")
            faculty_id = faculty_raw if faculty_raw and faculty_raw != _UNASSIGNED_FACULTY else None
            room_id = payload.get("roomId") or None
            day_of_week = int(payload.get("dayOfWeek") or 1)
            slot = _resolve_period_slot(
                branch, int(payload.get("periodIndex") or 1),
                payload.get("startTime"), payload.get("endTime"), user,
            )
            batch_subject = _resolve_batch_subject(branch, batch, subject, period, user)

            entry_id = payload.get("id")
            if entry_id:
                entry = tt_q.get_timetable_entry(branch.pk, entry_id)
                if entry is None:
                    return Response({"error": "Timetable slot not found."},
                                    status=status.HTTP_404_NOT_FOUND)
                tt_q.update_timetable_entry(entry, {
                    "batch_subject_id": batch_subject.id,
                    "period_slot_id": slot.id,
                    "day_of_week": day_of_week,
                    "faculty_id": faculty_id,
                    "room_id": room_id,
                    "status": "active",
                }, user=user)
                return Response({"id": str(entry.id)})

            timetable = tt_q.get_or_create_timetable(batch=batch, academic_period=period, user=user)
            entry = tt_q.create_timetable_entry(
                timetable=timetable, batch_subject=batch_subject, period_slot=slot,
                day_of_week=day_of_week, faculty_id=faculty_id, room_id=room_id, user=user,
            )
            return Response({"id": str(entry.id)}, status=status.HTTP_201_CREATED)

        if action == "create_substitution":
            entry = tt_q.get_timetable_entry(branch.pk, payload.get("timetableSlotId"))
            if entry is None:
                return Response({"error": "Timetable slot not found."},
                                status=status.HTTP_404_NOT_FOUND)
            sub = extra_q.create_substitution(
                branch=branch, timetable_entry=entry,
                original_faculty_id=entry.faculty_id,
                substitute_faculty_id=payload.get("substituteFacultyUserId"),
                date=_date(payload.get("date")), reason=payload.get("reason", ""), user=user,
            )
            return Response({"id": str(sub.id), "status": sub.status},
                            status=status.HTTP_201_CREATED)

        if action == "cancel_substitution":
            sub = extra_q.get_substitution(branch.pk, request.data.get("substitutionId"))
            if sub is None:
                return Response({"error": "Substitution not found."},
                                status=status.HTTP_404_NOT_FOUND)
            extra_q.cancel_substitution(sub, user=user)
            return Response({"id": str(sub.id), "status": "cancelled"})

        if action == "upload_study_material":
            batch = struct_q.get_batch(branch.pk, payload.get("classSectionId"))
            if batch is None:
                return Response({"error": "Class not found."},
                                status=status.HTTP_404_NOT_FOUND)
            material = extra_q.create_study_material(
                branch=branch, batch=batch,
                file_name=payload.get("fileName", "material"),
                s3_key=payload.get("s3Key", ""), url=payload.get("url", ""), user=user,
            )
            return Response({"id": str(material.id)}, status=status.HTTP_201_CREATED)

        if action == "delete_study_material":
            material = extra_q.get_study_material(branch.pk, request.data.get("materialId"))
            if material is None:
                return Response({"error": "Study material not found."},
                                status=status.HTTP_404_NOT_FOUND)
            extra_q.delete_study_material(material, user=user)
            return Response({"ok": True})

        return Response({"error": "Unknown or unsupported action."},
                        status=status.HTTP_400_BAD_REQUEST)
