"""Faculty marks — internal-assessment foundation.

GET returns FacultyMarksData split into myClass (homeroom read-only) and
classesITeach (subject-teacher entry). POST saves an internal mark with the
F-253 deadline rule (blocked past deadline unless an admin overrides).
"""

import datetime

from django.db.models import Q
from django.utils import timezone
from rest_framework import status as http
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import BatchFaculty
from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import faculty_teaching as ft_q
from apps.academics.scoping import resolve_branch
from apps.accounts.models.profile import StudentProfile
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.examinations.models import ExamScheduleSlot
from apps.examinations.queries import internal as int_q
from apps.examinations.queries import marks as marks_q


def _class_label(student_profile) -> str:
    enrollment = get_active_enrollment_for_profile(student_profile.pk)
    if enrollment and enrollment.batch_id:
        batch = enrollment.batch
        if batch.course_id:
            return f"{batch.course.name} - {batch.name}"
        return batch.name
    return ""


def _row(m) -> dict:
    return {
        "studentId": str(m.student_profile_id),
        "studentName": m.student_profile.user.full_name,
        "classLabel": _class_label(m.student_profile),
        "subjectId": str(m.subject_id),
        "subjectName": m.subject.name,
        "marks": float(m.marks) if m.marks is not None else None,
        "maxMarks": m.max_marks,
        "updatedAt": m.updated_at.isoformat(),
        "hardDeadlineAt": m.hard_deadline_at.isoformat() if m.hard_deadline_at else "",
        "recordedByName": m.recorded_by.full_name if m.recorded_by_id else "",
    }


def _faculty_teaching_pairs(user_id):
    """(subject_id, batch_id) pairs the faculty teaches, from their assignments."""
    pairs = set()
    for bf in BatchFaculty.objects.filter(
        faculty_id=user_id, is_active=True,
    ).select_related("batch_subject"):
        bs = bf.batch_subject
        pairs.add((bs.subject_id, bs.batch_id))
    return pairs


def _exam_slot_option(slot, now) -> dict:
    exam = slot.exam
    deadline = exam.marks_deadline
    batch = slot.batch
    batch_label = f"{batch.course.name} - {batch.name}" if batch.course_id else batch.name
    return {
        "id": str(slot.id),
        "label": f"{exam.name} — {slot.subject.name} ({batch_label})",
        "marksEntryDeadlineAt": deadline.isoformat() if deadline else "",
        "entryLocked": bool(deadline and deadline < now),
    }


def _exam_entry(m, slot) -> dict:
    batch = m.student.batch if m.student.batch_id else slot.batch
    batch_label = f"{batch.course.name} - {batch.name}" if batch and batch.course_id else (batch.name if batch else "")
    return {
        "examSlotId": str(slot.id),
        "studentId": str(m.student.student_profile_id),
        "studentName": m.student.user.full_name,
        "classLabel": batch_label,
        "subjectName": m.subject.name,
        "marks": None if m.is_absent or m.marks is None else float(m.marks),
        "maxMarks": float(slot.max_marks),
        "updatedAt": m.updated_at.isoformat(),
    }


def _exam_data_for_pairs(branch_id, pairs, now):
    exam_slots, exam_entries = [], []
    if not pairs:
        return exam_slots, exam_entries
    slot_q = Q()
    for subject_id, batch_id in pairs:
        slot_q |= Q(subject_id=subject_id, batch_id=batch_id)
    slots = (
        ExamScheduleSlot.objects.filter(exam__branch_id=branch_id, is_active=True)
        .filter(slot_q)
        .select_related("exam", "subject", "batch", "batch__course")
        .order_by("start_at")
    )
    for slot in slots:
        exam_slots.append(_exam_slot_option(slot, now))
        for m in marks_q.list_marks_for_slot_by_exam_subject(
            slot.exam_id, slot.subject_id, slot.batch_id,
        ):
            exam_entries.append(_exam_entry(m, slot))
    return exam_slots, exam_entries


def _exam_data_for_batches(branch_id, batch_ids, now):
    exam_slots, exam_entries = [], []
    for slot in marks_q.list_exam_slots_for_batches(branch_id, batch_ids):
        exam_slots.append(_exam_slot_option(slot, now))
        for m in marks_q.list_marks_for_slot_by_exam_subject(
            slot.exam_id, slot.subject_id, slot.batch_id,
        ):
            exam_entries.append(_exam_entry(m, slot))
    return exam_slots, exam_entries


class FacultyMarksView(APIView):
    """GET → FacultyMarksData (my class read-only + classes I teach editable)."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        faculty_id = request.user.pk
        now = timezone.now()
        is_college = branch.tenant.institution_type == "college"

        homerooms = ft_q.homeroom_batches(branch.pk, faculty_id)
        homeroom_ids = [b.id for b in homerooms]
        my_exam_slots, my_exam_entries = _exam_data_for_batches(branch.pk, homeroom_ids, now)
        my_internal = (
            [_row(m) for m in int_q.list_for_batches(branch.pk, homeroom_ids)]
            if is_college
            else []
        )

        pairs = _faculty_teaching_pairs(faculty_id)
        teach_exam_slots, teach_exam_entries = _exam_data_for_pairs(branch.pk, pairs, now)
        teach_internal = (
            [_row(m) for m in int_q.list_recorded_by(branch.pk, faculty_id)]
            if is_college
            else []
        )

        return Response({
            "facultyUserId": str(faculty_id),
            "myClass": {
                "homerooms": ft_q.homerooms_payload(homerooms),
                "examSlots": my_exam_slots,
                "examEntries": my_exam_entries,
                "internal": my_internal,
                "canEdit": False,
            },
            "classesITeach": {
                "teachingClasses": ft_q.teaching_classes_grouped(branch.pk, faculty_id),
                "examSlots": teach_exam_slots,
                "examEntries": teach_exam_entries,
                "internal": teach_internal,
                "canEdit": True,
            },
        })


class FacultyInternalMarkSaveView(APIView):
    """POST { studentId, subjectId, marks, maxMarks? } → save an internal mark (F-253)."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        if branch.tenant.institution_type != "college":
            raise PermissionDenied(
                "Internal marks are not used for schools. Enter marks under scheduled exams instead."
            )

        student_id = request.data.get("studentId")
        subject_id = request.data.get("subjectId")
        if not student_id or not subject_id:
            raise ValidationError({"studentId": "studentId and subjectId are required."})

        profile = StudentProfile.objects.filter(pk=student_id, is_active=True).first()
        subject = curr_q.get_subject(branch.pk, subject_id)
        if profile is None or subject is None:
            raise ValidationError({"studentId": "Student or subject not found."})

        enrollment = get_active_enrollment_for_profile(profile.pk)
        is_admin = IsAdminOrSuperAdmin().has_permission(request, self)
        if enrollment and enrollment.batch_id and not is_admin:
            if not ft_q.faculty_teaches_batch_subject(
                branch.pk, request.user.pk, enrollment.batch_id, subject_id,
            ):
                raise PermissionDenied(
                    "You can only enter internal marks for subjects you teach in that class."
                )

        existing = int_q.get_for_student_subject(branch.pk, profile.pk, subject.pk)
        if (existing and existing.hard_deadline_at
                and existing.hard_deadline_at < timezone.now() and not is_admin):
            raise ValidationError(
                "Internal marks entry deadline has passed. Contact an administrator to update marks.")

        marks = request.data.get("marks")
        obj = int_q.upsert(
            branch=branch, student_profile=profile, subject=subject,
            marks=marks, max_marks=request.data.get("maxMarks", 100),
            hard_deadline_at=existing.hard_deadline_at if existing else None,
            user=request.user,
        )
        return Response({"mark": _row(obj)}, status=http.HTTP_201_CREATED)
