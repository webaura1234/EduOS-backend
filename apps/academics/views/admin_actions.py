"""Admin Academics write actions for the gap domains: working days, substitutions,
study materials. (Periods/departments/subjects/timetable/holidays have their own
dedicated endpoints already.)"""

import datetime

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import DepartmentType, SubjectType
from apps.academics.queries import substitution_availability as avail_q
from apps.academics.queries import admin_extras as extra_q
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import syllabus as syl_q
from apps.academics.queries import timetable as tt_q
from apps.academics.helpers import batch_display_label, is_school
from apps.academics.interactors import curriculum as curr_i
from apps.academics.interactors import structure as struct_i
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


def _resolve_period(branch, period_id=None):
    year = cal_q.get_current_year(branch.pk)
    if year is None:
        return None
    if period_id:
        return cal_q.get_period(year.pk, period_id)
    return cal_q.resolve_current_period(year.pk)


def _subject_teacher_payload(assignment) -> dict:
    bs = assignment.batch_subject
    return {
        "id": str(assignment.id),
        "classSectionId": str(bs.batch_id),
        "subjectId": str(bs.subject_id),
        "facultyUserId": str(assignment.faculty_id),
        "academicPeriodId": str(bs.academic_period_id),
        "assignedAt": assignment.assigned_at.isoformat(),
        "batchSubjectId": str(bs.id),
        "version": assignment.version,
    }


def _class_teacher_payload(batch) -> dict:
    return {
        "classSectionId": str(batch.id),
        "classLabel": batch_display_label(batch),
        "teacherUserId": str(batch.class_teacher_id),
        "teacherName": batch.class_teacher.full_name,
        "assignedAt": batch.updated_at.isoformat(),
    }


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


def _subject_payload(branch, subject) -> dict:
    units = list(syl_q.units_for_subject(branch.pk, subject.pk))
    batches = syl_q.batches_by_subject(branch.pk, [subject.pk]).get(subject.pk, [])
    batch_ids = [b.pk for b in batches]
    progress_map = syl_q.progress_for_batches(branch.pk, batch_ids, [subject.pk])
    section_progress = []
    for batch in batches:
        completed = progress_map.get(batch.pk, {}).get(subject.pk, set())
        percent, done = syl_q.completion_stats(units, completed)
        section_progress.append({
            "classSectionId": str(batch.id),
            "label": batch_display_label(batch),
            "syllabusCompletionPercent": percent,
            "completedUnitIds": done,
        })
    return {
        "id": str(subject.id),
        "code": subject.code,
        "name": subject.name,
        "grade": subject.course.name if subject.course_id else None,
        "courseId": str(subject.course_id) if subject.course_id else None,
        "credits": subject.credits,
        "archived": not subject.is_active,
        "hasMarks": curr_q.subject_has_marks(subject.pk),
        "syllabusUnits": [syl_q.unit_dict(u) for u in units],
        "sectionProgress": section_progress,
        "syllabusCompletionPercent": 0,
        "completedUnitIds": [],
    }


def _batch_section_payload(batch) -> dict:
    return {
        "id": str(batch.id),
        "label": batch_display_label(batch),
        "departmentId": str(batch.course.department_id),
        "courseId": str(batch.course_id),
        "grade": batch.course.name,
        "section": batch.name,
        "academicYearId": str(batch.academic_year_id),
    }


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
            sid = payload.get("id")
            code = (payload.get("code") or "").strip()
            name = (payload.get("name") or "").strip()
            if sid:
                subj = curr_q.get_subject(branch.pk, sid)
                if subj is None:
                    return Response({"error": "Subject not found."}, status=status.HTTP_404_NOT_FOUND)
                if code and curr_q.subject_code_exists(subj.course_id, code, exclude_id=subj.pk):
                    return Response(
                        {"error": "A subject with this code already exists for this grade."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                curr_q.update_subject(subj, {
                    "name": name or subj.name,
                    "code": code or subj.code,
                    "credits": payload.get("credits"),
                }, user=user)
            else:
                course_id = payload.get("courseId")
                if not course_id:
                    return Response(
                        {"error": "courseId is required when creating a subject."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                course = struct_q.get_course(branch.pk, course_id)
                if course is None:
                    return Response({"error": "Grade/program not found."}, status=status.HTTP_404_NOT_FOUND)
                if code and curr_q.subject_code_exists(course.pk, code):
                    return Response(
                        {"error": "A subject with this code already exists for this grade."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                subj = curr_q.create_subject(
                    course=course, name=name or "Subject",
                    code=code, subject_type=SubjectType.THEORY,
                    credits=payload.get("credits"), user=user,
                )
            if "syllabusUnits" in payload:
                try:
                    syl_q.sync_units_for_subject(branch, subj, payload.get("syllabusUnits"), user=user)
                except ValueError as exc:
                    return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            subj = curr_q.get_subject(branch.pk, subj.pk)
            return Response(_subject_payload(branch, subj), status=status.HTTP_201_CREATED if not sid else status.HTTP_200_OK)

        if action == "update_syllabus_completion":
            subject_id = payload.get("subjectId")
            batch_id = payload.get("classSectionId")
            if not subject_id or not batch_id:
                return Response(
                    {"error": "subjectId and classSectionId are required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                units = syl_q.set_completion(
                    branch.pk, batch_id, subject_id,
                    payload.get("completedUnitIds", []), user=user,
                )
            except ValueError as exc:
                return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            completed = syl_q.completed_ids_for_batch(branch.pk, batch_id, subject_id)
            percent, done = syl_q.completion_stats(units, completed)
            return Response({
                "syllabusCompletionPercent": percent,
                "completedUnitIds": done,
            })

        if action == "save_class_section":
            tenant = branch.tenant
            sid = payload.get("id")
            if sid:
                batch = struct_q.get_batch(branch.pk, sid)
                if batch is None:
                    return Response({"error": "Class section not found."}, status=status.HTTP_404_NOT_FOUND)
                if is_school(tenant):
                    section_name = (payload.get("section") or payload.get("label") or batch.name).strip()
                    if not section_name:
                        return Response({"error": "Section is required."}, status=status.HTTP_400_BAD_REQUEST)
                    if struct_q.batch_name_exists(
                        batch.course_id, batch.academic_year_id, section_name, exclude_id=batch.pk,
                    ):
                        return Response(
                            {"error": "This section already exists for the grade in the current academic year."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    struct_q.update_batch(batch, {"name": section_name}, user=user)
                else:
                    name = payload.get("label") or payload.get("name") or batch.name
                    struct_q.update_batch(batch, {"name": name}, user=user)
                batch = struct_q.get_batch(branch.pk, batch.pk)
                return Response(_batch_section_payload(batch))

            year = cal_q.get_current_year(branch.pk)
            if year is None:
                return Response(
                    {"error": "Set a current academic year before creating class sections."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if is_school(tenant):
                grade = (payload.get("grade") or payload.get("label") or "").strip()
                if not grade:
                    return Response(
                        {"error": "Grade is required (e.g. Class 5)."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                dept = struct_q.get_department(branch.pk, payload.get("departmentId"))
                if dept is None:
                    return Response({"error": "Stream not found."}, status=status.HTTP_404_NOT_FOUND)
                section = (payload.get("section") or "A").strip().upper() or "A"
                course = struct_q.get_or_create_course_in_department(dept, grade, user=user)
                if struct_q.batch_name_exists(course.pk, year.pk, section):
                    return Response(
                        {"error": f"Section {section} already exists for {grade} in the current academic year."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                batch = struct_q.create_batch(
                    course=course, academic_year=year, name=section, user=user,
                )
                batch = struct_q.get_batch(branch.pk, batch.pk)
                return Response(_batch_section_payload(batch), status=status.HTTP_201_CREATED)

            # College — program + cohort label on the batch row.
            name = payload.get("label") or payload.get("name") or "Section"
            course = _resolve_course(branch, payload.get("departmentId"), user)
            batch = struct_q.create_batch(
                course=course, academic_year=year, name=name, user=user,
            )
            batch = struct_q.get_batch(branch.pk, batch.pk)
            return Response(_batch_section_payload(batch), status=status.HTTP_201_CREATED)

        if action == "assign_class_teacher":
            if not is_school(branch.tenant):
                return Response(
                    {"error": "Class teachers are only used for schools."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            batch = struct_q.get_batch(branch.pk, payload.get("classSectionId"))
            if batch is None:
                return Response({"error": "Class section not found."}, status=status.HTTP_404_NOT_FOUND)
            teacher_id = payload.get("teacherUserId")
            if not teacher_id:
                return Response({"error": "teacherUserId is required."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                struct_i.update_batch(
                    branch.tenant, batch, fields={"class_teacher_id": teacher_id}, user=user,
                )
            except Exception as exc:
                from rest_framework.exceptions import ValidationError
                if isinstance(exc, ValidationError):
                    detail = exc.detail
                    msg = detail.get("classTeacherId", detail) if isinstance(detail, dict) else str(detail)
                    return Response({"error": str(msg)}, status=status.HTTP_400_BAD_REQUEST)
                raise
            batch = struct_q.get_batch(branch.pk, batch.pk)
            return Response(_class_teacher_payload(batch))

        if action == "unassign_class_teacher":
            if not is_school(branch.tenant):
                return Response(
                    {"error": "Class teachers are only used for schools."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            batch = struct_q.get_batch(branch.pk, payload.get("classSectionId"))
            if batch is None:
                return Response({"error": "Class section not found."}, status=status.HTTP_404_NOT_FOUND)
            try:
                struct_i.update_batch(
                    branch.tenant, batch, fields={"class_teacher_id": None}, user=user,
                )
            except Exception as exc:
                from rest_framework.exceptions import ValidationError
                if isinstance(exc, ValidationError):
                    return Response({"error": str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
                raise
            return Response({"ok": True})

        if action == "assign_subject_teacher":
            batch = struct_q.get_batch(branch.pk, payload.get("classSectionId"))
            if batch is None:
                return Response({"error": "Class section not found."}, status=status.HTTP_404_NOT_FOUND)
            subject = curr_q.get_subject(branch.pk, payload.get("subjectId"))
            if subject is None:
                return Response({"error": "Subject not found."}, status=status.HTTP_404_NOT_FOUND)
            faculty_id = payload.get("facultyUserId")
            if not faculty_id:
                return Response({"error": "facultyUserId is required."}, status=status.HTTP_400_BAD_REQUEST)
            period = _resolve_period(branch, payload.get("academicPeriodId"))
            if period is None:
                return Response(
                    {"error": "Create a current academic year with at least one term/period first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            batch_subject = _resolve_batch_subject(branch, batch, subject, period, user)
            assigned_at = _date(payload.get("assignedAt"))
            try:
                assignment = curr_i.upsert_primary_batch_faculty(
                    branch.tenant.pk,
                    batch_subject,
                    faculty_id=faculty_id,
                    assigned_at=assigned_at,
                    user=user,
                )
            except Exception as exc:
                from rest_framework.exceptions import ValidationError
                if isinstance(exc, ValidationError):
                    detail = exc.detail
                    msg = detail.get("facultyId", detail) if isinstance(detail, dict) else str(detail)
                    return Response({"error": str(msg)}, status=status.HTTP_400_BAD_REQUEST)
                raise
            assignment = curr_q.get_batch_faculty(branch.pk, assignment.pk)
            return Response(_subject_teacher_payload(assignment))

        if action == "unassign_subject_teacher":
            batch = struct_q.get_batch(branch.pk, payload.get("classSectionId"))
            if batch is None:
                return Response({"error": "Class section not found."}, status=status.HTTP_404_NOT_FOUND)
            subject = curr_q.get_subject(branch.pk, payload.get("subjectId"))
            if subject is None:
                return Response({"error": "Subject not found."}, status=status.HTTP_404_NOT_FOUND)
            period = _resolve_period(branch, payload.get("academicPeriodId"))
            if period is None:
                return Response(
                    {"error": "Create a current academic year with at least one term/period first."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            batch_subject = (
                curr_q.list_batch_subjects(
                    branch.pk, batch_id=batch.id, academic_period_id=period.id,
                )
                .filter(subject_id=subject.id)
                .first()
            )
            if batch_subject is None:
                return Response({"ok": True})
            try:
                curr_i.end_primary_batch_faculty(batch_subject, user=user)
            except Exception as exc:
                from rest_framework.exceptions import ValidationError
                if isinstance(exc, ValidationError):
                    return Response({"error": str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
                raise
            return Response({"ok": True})

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
            sub_date = _date(payload.get("date"))
            if entry.day_of_week != sub_date.weekday():
                return Response(
                    {"error": "Selected date does not match this session's weekday."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            substitute_id = payload.get("substituteFacultyUserId")
            from apps.accounts.models.user import Role, User
            try:
                substitute = User.objects.get(
                    pk=substitute_id,
                    tenant=branch.tenant,
                    branch=branch,
                    role=Role.FACULTY,
                    is_active=True,
                )
            except (User.DoesNotExist, ValueError, TypeError):
                return Response({"error": "Substitute faculty not found."},
                                status=status.HTTP_404_NOT_FOUND)
            if not avail_q.is_faculty_available_for_substitution(
                branch=branch,
                faculty_user=substitute,
                timetable_entry=entry,
                on_date=sub_date,
            ):
                return Response(
                    {"error": "Selected faculty is not available for this session."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            sub = extra_q.create_substitution(
                branch=branch, timetable_entry=entry,
                original_faculty_id=entry.faculty_id,
                substitute_faculty_id=substitute_id,
                date=sub_date, reason=payload.get("reason", ""), user=user,
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

        if action == "create_study_folder":
            batch = struct_q.get_batch(branch.pk, payload.get("classSectionId"))
            if batch is None:
                return Response({"error": "Class not found."}, status=status.HTTP_404_NOT_FOUND)
            name = (payload.get("name") or "").strip()
            if not name:
                return Response({"error": "Folder name is required."}, status=status.HTTP_400_BAD_REQUEST)
            if extra_q.folder_name_taken(batch.pk, name):
                return Response({"error": "A folder with this name already exists for the class."},
                                status=status.HTTP_400_BAD_REQUEST)
            folder = extra_q.create_folder(branch=branch, batch=batch, name=name, user=user)
            return Response({"id": str(folder.id), "name": folder.name}, status=status.HTTP_201_CREATED)

        if action == "rename_study_folder":
            folder = extra_q.get_folder(branch.pk, payload.get("folderId"))
            if folder is None:
                return Response({"error": "Folder not found."}, status=status.HTTP_404_NOT_FOUND)
            name = (payload.get("name") or "").strip()
            if not name:
                return Response({"error": "Folder name is required."}, status=status.HTTP_400_BAD_REQUEST)
            if extra_q.folder_name_taken(folder.batch_id, name, exclude_id=folder.pk):
                return Response({"error": "A folder with this name already exists for the class."},
                                status=status.HTTP_400_BAD_REQUEST)
            folder = extra_q.rename_folder(folder, name, user=user)
            return Response({"id": str(folder.id), "name": folder.name})

        if action == "delete_study_folder":
            folder = extra_q.get_folder(branch.pk, request.data.get("folderId"))
            if folder is None:
                return Response({"error": "Folder not found."}, status=status.HTTP_404_NOT_FOUND)
            if extra_q.folder_material_count(folder.pk) > 0:
                return Response(
                    {"error": "Remove or delete all files in this folder before deleting it."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            extra_q.delete_folder(folder, user=user)
            return Response({"ok": True})

        if action == "upload_study_material":
            batch = struct_q.get_batch(branch.pk, payload.get("classSectionId"))
            if batch is None:
                return Response({"error": "Class not found."},
                                status=status.HTTP_404_NOT_FOUND)
            folder = None
            folder_id = payload.get("folderId")
            if folder_id:
                folder = extra_q.get_folder(branch.pk, folder_id)
                if folder is None or folder.batch_id != batch.pk:
                    return Response({"error": "Folder not found for this class."},
                                    status=status.HTTP_404_NOT_FOUND)
            material = extra_q.create_study_material(
                branch=branch, batch=batch, folder=folder,
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
