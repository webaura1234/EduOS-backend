"""Tab-scoped admin academics GET endpoints for lazy-loaded UI tabs."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.interactors import timetable as tt_i
from apps.academics.interactors.study_materials import folder_summary
from apps.academics.queries import admin_extras as extra_q
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import holiday as hol_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import syllabus as syl_q
from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.academics.views.admin_overview import (
    _calendar_change,
    _class_section,
    _class_teacher,
    _period,
    _review_queue,
    _study_material,
    _subject,
    _subject_teacher,
    _substitution,
    _timetable_slot,
    _working_days,
)
from apps.accounts.models.user import Role, User
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.examinations.queries import marks as exam_marks_q


def _branch_context(request):
    branch = resolve_branch(request)
    tenant = branch.tenant
    is_college = tenant.institution_type == "college"
    current_year = cal_q.get_current_year(branch.pk)
    current_period = (
        cal_q.resolve_current_period(current_year.pk) if current_year else None
    )
    return branch, tenant, is_college, current_year, current_period


def _faculty_list(tenant, branch):
    return [
        {"userId": str(u.id), "name": u.full_name}
        for u in User.objects.filter(
            tenant_id=tenant.id,
            branch_id=branch.pk,
            role=Role.FACULTY,
            is_active=True,
        ).order_by("first_name", "last_name")
    ]


def _batches(branch):
    return list(
        struct_q.list_batches(branch.pk).select_related(
            "course", "course__department", "class_teacher",
        )
    )


class AdminAcademicsCalendarTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch, tenant, is_college, current_year, current_period = _branch_context(request)
        years = list(cal_q.list_years(branch.pk))
        periods = list(cal_q.list_periods(current_year.pk)) if current_year else []
        batches = _batches(branch)
        subjects = list(curr_q.list_subjects(branch.pk))
        return Response({
            "institutionType": tenant.institution_type,
            "hierarchyLabel": "Department" if is_college else "Stream",
            "periodKind": "semester" if is_college else "term",
            "academicYears": [{"id": str(y.id), "label": y.name} for y in years],
            "periods": [_period(p) for p in periods],
            "holidays": [
                {
                    "id": str(h.id),
                    "name": h.name,
                    "date": h.date.isoformat(),
                    "holidayType": h.holiday_type,
                }
                for h in hol_q.list_holidays(branch.pk)
            ],
            "workingDays": _working_days(branch),
            "calendarChanges": [
                _calendar_change(c) for c in extra_q.list_calendar_changes(branch.pk)
            ],
            "attendanceFrozenThrough": (
                frozen.isoformat()
                if (frozen := extra_q.latest_frozen_through(branch.pk)) else None
            ),
            "currentPeriodId": str(current_period.pk) if current_period else None,
            "classSections": [_class_section(b) for b in batches],
            "subjects": [
                {"id": str(s.id), "name": s.name, "courseId": str(s.course_id), "grade": s.course.name}
                for s in subjects if s.is_active
            ],
            "faculty": _faculty_list(tenant, branch),
            "rooms": [{"id": str(r.id), "name": r.name} for r in tt_q.list_rooms(branch.pk)],
            "timetableSlots": [
                _timetable_slot(e) for e in tt_q.list_active_entries_for_branch(branch.pk)
            ],
            "substitutions": [
                _substitution(s) for s in extra_q.list_substitutions(branch.pk)
            ],
            "subjectTeachers": [
                _subject_teacher(a)
                for a in curr_q.list_batch_faculty(branch.pk, active_primary=True)
            ],
        })


class AdminAcademicsStructureTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch, tenant, is_college, _, _ = _branch_context(request)
        batches = _batches(branch)
        return Response({
            "institutionType": tenant.institution_type,
            "hierarchyLabel": "Department" if is_college else "Stream",
            "departments": [
                {
                    "id": str(d.id),
                    "name": d.name,
                    "parentId": str(d.parent_id) if d.parent_id else None,
                }
                for d in struct_q.list_departments(branch.pk)
            ],
            "classSections": [_class_section(b) for b in batches],
        })


class AdminAcademicsStaffingTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch, tenant, is_college, current_year, current_period = _branch_context(request)
        periods = list(cal_q.list_periods(current_year.pk)) if current_year else []
        batches = _batches(branch)
        subjects = list(curr_q.list_subjects(branch.pk))
        class_teachers = []
        if not is_college:
            for batch in batches:
                row = _class_teacher(batch)
                if row:
                    class_teachers.append(row)
        return Response({
            "institutionType": tenant.institution_type,
            "hierarchyLabel": "Department" if is_college else "Stream",
            "periodKind": "semester" if is_college else "term",
            "periods": [_period(p) for p in periods],
            "faculty": _faculty_list(tenant, branch),
            "classSections": [_class_section(b) for b in batches],
            "classTeachers": class_teachers,
            "subjectTeachers": [
                _subject_teacher(a)
                for a in curr_q.list_batch_faculty(branch.pk, active_primary=True)
            ],
            "subjects": [
                {"id": str(s.id), "name": s.name, "courseId": str(s.course_id), "grade": s.course.name}
                for s in subjects if s.is_active
            ],
            "currentPeriodId": str(current_period.pk) if current_period else None,
            "adminReviewQueue": _review_queue(
                branch.pk, academic_period_id=current_period.pk if current_period else None,
            ),
        })


class AdminAcademicsSubjectsTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch, tenant, is_college, _, _ = _branch_context(request)
        batches = _batches(branch)
        batch_ids = [b.pk for b in batches]
        subjects = list(curr_q.list_subjects(branch.pk))
        subject_ids = [s.id for s in subjects]
        marked_subject_ids = exam_marks_q.subjects_with_marks(subject_ids)
        units_map = syl_q.units_by_subject(branch.pk, subject_ids)
        batches_map = syl_q.batches_by_subject(branch.pk, subject_ids)
        progress_map = syl_q.progress_for_batches(branch.pk, batch_ids, subject_ids)
        return Response({
            "institutionType": tenant.institution_type,
            "hierarchyLabel": "Department" if is_college else "Stream",
            "classSections": [_class_section(b) for b in batches],
            "subjects": [
                _subject(
                    s,
                    units=units_map.get(s.id, []),
                    batches=batches_map.get(s.id, []),
                    progress_map=progress_map,
                    has_marks=s.id in marked_subject_ids,
                )
                for s in subjects
            ],
        })


class AdminAcademicsTimetableTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch, tenant, is_college, current_year, current_period = _branch_context(request)
        periods = list(cal_q.list_periods(current_year.pk)) if current_year else []
        batches = _batches(branch)
        subjects = list(curr_q.list_subjects(branch.pk))
        clashes = [c.to_dict() for c in tt_i.list_all_clashes(branch.pk)]
        return Response({
            "institutionType": tenant.institution_type,
            "periodKind": "semester" if is_college else "term",
            "periods": [_period(p) for p in periods],
            "currentPeriodId": str(current_period.pk) if current_period else None,
            "classSections": [_class_section(b) for b in batches],
            "subjects": [
                {"id": str(s.id), "name": s.name, "courseId": str(s.course_id), "grade": s.course.name}
                for s in subjects if s.is_active
            ],
            "rooms": [{"id": str(r.id), "name": r.name} for r in tt_q.list_rooms(branch.pk)],
            "faculty": _faculty_list(tenant, branch),
            "workingDays": _working_days(branch),
            "subjectTeachers": [
                _subject_teacher(a)
                for a in curr_q.list_batch_faculty(branch.pk, active_primary=True)
            ],
            "timetableSlots": [
                _timetable_slot(e) for e in tt_q.list_active_entries_for_branch(branch.pk)
            ],
            "clashes": clashes,
            "adminReviewQueue": _review_queue(
                branch.pk, academic_period_id=current_period.pk if current_period else None,
            ),
        })


class AdminAcademicsStudyMaterialsTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch, _, _, _, _ = _branch_context(request)
        batches = _batches(branch)
        return Response({
            "classSections": [_class_section(b) for b in batches],
            "studyMaterialFolders": [
                folder_summary(f, f.material_count)
                for f in extra_q.list_folders_for_branch(branch.pk)
            ],
            "studyMaterials": [
                _study_material(m) for m in extra_q.list_study_materials(branch.pk)
            ],
        })


class AdminAcademicsSubstitutionsTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch, tenant, _, _, _ = _branch_context(request)
        subjects = list(curr_q.list_subjects(branch.pk))
        return Response({
            "faculty": _faculty_list(tenant, branch),
            "subjects": [
                {"id": str(s.id), "name": s.name} for s in subjects if s.is_active
            ],
            "timetableSlots": [
                _timetable_slot(e) for e in tt_q.list_active_entries_for_branch(branch.pk)
            ],
            "substitutions": [
                _substitution(s) for s in extra_q.list_substitutions(branch.pk)
            ],
        })
