"""Interactors — student/parent examination hubs (read-only)."""

from __future__ import annotations

from django.utils import timezone

from apps.academics.helpers import is_college
from apps.admissions.queries import enrollment as enrollment_q
from apps.examinations.helpers import split_datetime
from apps.examinations.interactors.assignment import serialize_assignment, serialize_submission
from apps.examinations.queries import assignment as asg_q
from apps.examinations.queries import hub as hub_q
from apps.examinations.queries import result as result_q
from apps.examinations.services import grading as grading_svc


def _institution_type(tenant) -> str:
    return "college" if is_college(tenant) else "school"


def _enrollment_id(student_profile):
    """The student's active enrollment id (exam rows key off StudentEnrollment)."""
    enr = enrollment_q.resolve_enrollment_for_profile(student_profile)
    return enr.pk if enr else None


def _serialize_slot(slot) -> dict:
    date, start_time, _ = split_datetime(slot.start_at)
    local_end = timezone.localtime(slot.end_at)
    return {
        "id": str(slot.pk),
        "name": f"{slot.exam.name} — {slot.subject.name}",
        "classSectionId": str(slot.batch_id),
        "classLabel": slot.batch.name,
        "subjectId": str(slot.subject_id),
        "subjectName": slot.subject.name,
        "date": date,
        "startTime": start_time,
        "endTime": local_end.strftime("%H:%M"),
        "roomId": str(slot.room_id),
        "status": "published" if slot.exam.is_published else "draft",
    }


def _published_result_rows(student_profile) -> list[dict]:
    rows: list[dict] = []
    enr_id = _enrollment_id(student_profile)
    if not enr_id:
        return rows
    marks_entries = list(hub_q.list_published_marks_for_student(enr_id))
    for entry in marks_entries:
        batch_id = student_profile.current_batch_id
        slot = hub_q.get_slot_for_exam_subject_batch(entry.exam_id, entry.subject_id, batch_id)
        if not slot:
            continue
        publication = result_q.get_current_publication(entry.exam_id)
        published_at = publication.published_at.isoformat() if publication else ""
        if entry.is_absent or entry.marks is None:
            percent = None
            remark = "AB"
        else:
            final_marks = entry.marks
            if entry.grace_applied:
                final_marks = entry.marks + entry.grace_applied
            percent = (
                float(grading_svc.percent_of(final_marks, slot.max_marks))
                if grading_svc.percent_of(final_marks, slot.max_marks) is not None
                else None
            )
            remark = "OK"
        rows.append(
            {
                "examSlotId": str(slot.pk),
                "subjectName": entry.subject.name,
                "publishedAt": published_at,
                "percent": percent,
                "remark": remark,
            }
        )
    rows.sort(key=lambda r: r["publishedAt"], reverse=True)
    return rows


def _gpa_summary(student_profile, *, college: bool) -> dict | None:
    if not college:
        return None
    enr_id = _enrollment_id(student_profile)
    if not enr_id:
        return None
    results = list(hub_q.list_published_student_results(enr_id))
    gpas = [r.gpa for r in results if r.gpa is not None]
    if not gpas:
        return None
    sgpa = float(gpas[0])
    cgpa = float(sum(gpas) / len(gpas))
    latest = results[0].publication.published_at if results and results[0].publication else timezone.now()
    return {
        "sgpa": sgpa,
        "cgpa": round(cgpa, 2),
        "calculatedAt": latest.isoformat(),
    }


def build_exam_hub(student_profile, *, tenant) -> dict:
    batch = student_profile.current_batch
    branch = batch.course.department.branch if batch else None
    branch_id = branch.pk if branch else student_profile.user.branch_id
    enr_id = _enrollment_id(student_profile)
    exam_fee_paid = hub_q.student_exam_fees_paid(enr_id) if enr_id else True
    college = is_college(tenant)
    slots = (
        list(hub_q.list_upcoming_slots_for_batch(branch_id, batch.pk))
        if batch
        else []
    )
    return {
        "institutionType": _institution_type(tenant),
        "student": {
            "studentId": str(student_profile.pk),
            "name": student_profile.user.full_name,
            "classLabel": batch.name if batch else "",
            "examFeePaid": exam_fee_paid,
        },
        "upcomingExams": [_serialize_slot(s) for s in slots],
        "hallTicketAvailable": college and exam_fee_paid,
        "publishedResults": _published_result_rows(student_profile),
    }


def build_results_hub(student_profile, *, tenant) -> dict:
    college = is_college(tenant)
    return {
        "institutionType": _institution_type(tenant),
        "results": _published_result_rows(student_profile),
        "gpa": _gpa_summary(student_profile, college=college),
    }


def build_assignments_hub(student_profile, *, branch_id) -> dict:
    batch_id = student_profile.current_batch_id
    asg_q.close_past_due_assignments(branch_id)
    assignments = list(asg_q.list_assignments(branch_id, batch_id=batch_id))
    enr_id = _enrollment_id(student_profile)
    submissions = [
        s
        for s in asg_q.list_submissions_for_branch(branch_id)
        if enr_id and str(s.student_id) == str(enr_id)
    ]
    return {
        "assignments": [serialize_assignment(a) for a in assignments],
        "submissions": [serialize_submission(s) for s in submissions],
    }
