"""Faculty marks — internal-assessment foundation.

GET returns the FacultyMarksData shape (internal real; exam slots/entries empty
for now — the exam-marks aggregate is a separate piece). POST saves an internal mark
with the F-253 deadline rule (blocked past deadline unless an admin overrides).
"""

import datetime

from django.utils import timezone
from rest_framework import status as http
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Q

from apps.academics.models import BatchFaculty
from apps.academics.queries import curriculum as curr_q
from apps.academics.scoping import resolve_branch
from apps.accounts.models.profile import StudentProfile
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.examinations.models import ExamScheduleSlot
from apps.examinations.queries import internal as int_q
from apps.examinations.queries import marks as marks_q


def _class_label(student_profile) -> str:
    enrollment = get_active_enrollment_for_profile(student_profile.pk)
    return enrollment.batch.name if enrollment and enrollment.batch_id else ""


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
    return {
        "id": str(slot.id),
        "label": f"{exam.name} — {slot.subject.name} ({slot.batch.name})",
        "marksEntryDeadlineAt": deadline.isoformat() if deadline else "",
        "entryLocked": bool(deadline and deadline < now),
    }


def _exam_entry(m, slot) -> dict:
    return {
        "examSlotId": str(slot.id),
        "studentId": str(m.student.student_profile_id),
        "studentName": m.student.user.full_name,
        "classLabel": m.student.batch.name if m.student.batch_id else "",
        "subjectName": m.subject.name,
        "marks": None if m.is_absent or m.marks is None else float(m.marks),
        "maxMarks": float(slot.max_marks),
        "updatedAt": m.updated_at.isoformat(),
    }


class FacultyMarksView(APIView):
    """GET → FacultyMarksData (internal + exam slots/entries for the faculty's subjects)."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        now = timezone.now()
        internal = [_row(m) for m in int_q.list_recorded_by(branch.pk, request.user.pk)]

        # Exam slots for the subjects/batches this faculty teaches.
        pairs = _faculty_teaching_pairs(request.user.pk)
        exam_slots, exam_entries = [], []
        if pairs:
            slot_q = Q()
            for subject_id, batch_id in pairs:
                slot_q |= Q(subject_id=subject_id, batch_id=batch_id)
            slots = (
                ExamScheduleSlot.objects.filter(exam__branch_id=branch.pk, is_active=True)
                .filter(slot_q)
                .select_related("exam", "subject", "batch")
                .order_by("start_at")
            )
            for slot in slots:
                exam_slots.append(_exam_slot_option(slot, now))
                for m in marks_q.list_marks_for_slot_by_exam_subject(
                    slot.exam_id, slot.subject_id, slot.batch_id,
                ):
                    exam_entries.append(_exam_entry(m, slot))

        return Response({
            "examSlots": exam_slots,
            "examEntries": exam_entries,
            "internal": internal,
        })


class FacultyInternalMarkSaveView(APIView):
    """POST { studentId, subjectId, marks, maxMarks? } → save an internal mark (F-253)."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        student_id = request.data.get("studentId")
        subject_id = request.data.get("subjectId")
        if not student_id or not subject_id:
            raise ValidationError({"studentId": "studentId and subjectId are required."})

        profile = StudentProfile.objects.filter(pk=student_id, is_active=True).first()
        subject = curr_q.get_subject(branch.pk, subject_id)
        if profile is None or subject is None:
            raise ValidationError({"studentId": "Student or subject not found."})

        # F-253: block edits past the deadline unless the actor is an admin.
        existing = int_q.get_for_student_subject(branch.pk, profile.pk, subject.pk)
        is_admin = IsAdminOrSuperAdmin().has_permission(request, self)
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
