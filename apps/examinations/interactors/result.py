"""Interactors — result compute, two-step publish, revise, grace marks, analytics."""

from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.academics.helpers import is_college
from apps.admissions.queries import enrollment as enrollment_q
from apps.examinations.enums import MarksStatus, ResultStatus
from apps.examinations.exceptions import (
    ConfirmTokenRequiredError,
    GraceMarksCollegeOnlyError,
    InvalidConfirmTokenError,
    PublishJobInProgressError,
    PublishedResultDeleteError,
)
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import registration as reg_q
from apps.examinations.queries import result as result_q
from apps.examinations.services import grading as grading_svc
from apps.examinations.services.pdf import (
    generate_result_pdf,
    marksheet_file_key,
    report_card_file_key,
    store_result_pdf,
)

CONFIRM_TTL_SECONDS = 900
_CACHE_PREFIX = "exam_results_confirm:"


def _cache_key(exam_id) -> str:
    return f"{_CACHE_PREFIX}{exam_id}"


def _slot_map(exam_id) -> dict:
    return {
        (str(slot.subject_id), str(slot.batch_id)): slot
        for slot in exam_q.list_schedule_slots(exam_id)
    }


def _marks_snapshot_rows(entries) -> list[dict]:
    rows = []
    for entry in entries:
        rows.append(
            {
                "student_id": str(entry.student_id),
                "subject_id": str(entry.subject_id),
                "marks": str(entry.marks) if entry.marks is not None else None,
                "is_absent": entry.is_absent,
                "grace_applied": str(entry.grace_applied or 0),
                "marks_status": entry.marks_status,
            }
        )
    return rows


def _final_marks(entry, *, slot_max: Decimal, grace_max: int, pass_percent: Decimal) -> tuple[Decimal | None, Decimal]:
    if entry.is_absent or entry.marks is None:
        return None, Decimal("0")
    base = Decimal(str(entry.marks))
    stored_grace = Decimal(str(entry.grace_applied or 0))
    if stored_grace > 0:
        return grading_svc.bankers_round(base + stored_grace), stored_grace
    return grading_svc.compute_grace(
        marks=base,
        max_marks=slot_max,
        grace_max=grace_max,
        pass_percent=pass_percent,
    )


def _compute_for_student(
    *,
    student_id,
    entries,
    slots_by_subject_batch,
    grade_scale,
    college: bool,
    grace_max: int,
    pass_percent: Decimal,
    exclude_absent_from_gpa: bool,
) -> dict:
    subject_percents: list[Decimal | None] = []
    subject_gpa_rows: list[dict] = []
    arrear_subjects: list[dict] = []
    total_obtained = Decimal("0")
    total_max = Decimal("0")

    for entry in entries:
        batch_id = str(entry.student.current_batch_id) if entry.student.current_batch_id else ""
        slot = slots_by_subject_batch.get((str(entry.subject_id), batch_id))
        slot_max = Decimal(str(slot.max_marks)) if slot else Decimal(str(entry.subject.max_marks))
        final_marks, _grace = _final_marks(
            entry,
            slot_max=slot_max,
            grace_max=grace_max,
            pass_percent=pass_percent,
        )

        if entry.is_absent or final_marks is None:
            subject_percents.append(None)
            if college:
                subject_gpa_rows.append(
                    {"grade_point": None, "credits": entry.subject.credits, "is_absent": True}
                )
                arrear_subjects.append(
                    {"subjectId": str(entry.subject_id), "subjectName": entry.subject.name}
                )
            continue

        total_obtained += final_marks
        total_max += slot_max
        pct = grading_svc.percent_of(final_marks, slot_max)
        subject_percents.append(pct)

        pass_threshold = grading_svc.scaled_pass_marks(
            entry.subject.pass_marks, entry.subject.max_marks, slot_max
        )
        if final_marks < pass_threshold:
            arrear_subjects.append(
                {"subjectId": str(entry.subject_id), "subjectName": entry.subject.name}
            )

        if grade_scale and pct is not None:
            _grade, gp = grading_svc.lookup_grade(grade_scale.bands, pct)
            subject_gpa_rows.append(
                {
                    "grade_point": gp,
                    "credits": entry.subject.credits or 0,
                    "is_absent": False,
                }
            )

    percentage = (
        grading_svc.percent_of(total_obtained, total_max)
        if total_max > 0
        else grading_svc.compute_overall_percent(subject_percents)
    )
    overall_grade, _ = (
        grading_svc.lookup_grade(grade_scale.bands, percentage)
        if grade_scale and percentage is not None
        else ("", None)
    )
    gpa = (
        grading_svc.compute_sgpa(subject_gpa_rows, exclude_absent=exclude_absent_from_gpa)
        if college
        else None
    )
    is_pass = len(arrear_subjects) == 0 and (percentage is None or percentage >= pass_percent)

    return {
        "student_id": student_id,
        "total_marks": total_obtained,
        "percentage": percentage or Decimal("0"),
        "grade": overall_grade,
        "gpa": gpa,
        "is_pass": is_pass,
        "arrear_subjects": arrear_subjects,
    }


def _build_student_results(exam, *, college: bool, tenant) -> tuple[list[dict], str]:
    entries = list(result_q.list_submitted_marks_with_subjects(exam.pk))
    if not entries:
        raise ValidationError({"marks": "No submitted marks found for this exam."})

    slots_by_subject_batch = _slot_map(exam.pk)
    by_student: dict[str, list] = defaultdict(list)
    for entry in entries:
        by_student[str(entry.student_id)].append(entry)

    results: list[dict] = []
    for student_id, student_entries in by_student.items():
        student = student_entries[0].student
        course_id = student.current_batch.course_id if student.current_batch else None
        grade_scale = (
            result_q.get_grade_scale_for_course(exam.branch_id, course_id) if course_id else None
        )
        grace_max = grade_scale.grace_marks_max if grade_scale else 0
        pass_percent = Decimal("35")
        computed = _compute_for_student(
            student_id=student_id,
            entries=student_entries,
            slots_by_subject_batch=slots_by_subject_batch,
            grade_scale=grade_scale,
            college=college,
            grace_max=grace_max,
            pass_percent=pass_percent,
            exclude_absent_from_gpa=college,
        )
        computed["student"] = student
        results.append(computed)

    snapshot = grading_svc.snapshot_hash(_marks_snapshot_rows(entries))
    return results, snapshot


def _serialize_student_result(row, *, exam_id, publication_id=None) -> dict:
    student = row["student"]
    return {
        "studentId": str(student.student_profile_id),
        "studentName": student.user.full_name,
        "classLabel": student.current_batch.name if student.current_batch else "",
        "examId": str(exam_id),
        "publicationId": str(publication_id) if publication_id else None,
        "totalMarks": float(row["total_marks"]),
        "percentage": float(row["percentage"]),
        "grade": row["grade"],
        "gpa": float(row["gpa"]) if row["gpa"] is not None else None,
        "isPass": row["is_pass"],
        "arrearSubjects": row["arrear_subjects"],
    }


def _persist_student_results(
    *,
    exam,
    branch,
    institution_name: str,
    results: list[dict],
    publication_id,
    college: bool,
    user,
) -> list[dict]:
    serialized = []
    for row in results:
        report_key = ""
        marksheet_key = ""
        pdf = generate_result_pdf(
            title="Report Card" if not college else "Marksheet",
            institution_name=institution_name,
            exam_name=exam.name,
            student_name=row["student"].user.full_name,
            grade=row["grade"],
            percentage=str(row["percentage"]),
            gpa=str(row["gpa"]) if row["gpa"] is not None else "",
        )
        if college:
            marksheet_key = marksheet_file_key(
                branch_id=branch.pk, exam_id=exam.pk, student_id=row["student_id"]
            )
            store_result_pdf(key=marksheet_key, pdf_bytes=pdf)
        else:
            report_key = report_card_file_key(
                branch_id=branch.pk, exam_id=exam.pk, student_id=row["student_id"]
            )
            store_result_pdf(key=report_key, pdf_bytes=pdf)

        result_q.upsert_student_result(
            exam_id=exam.pk,
            student_id=row["student_id"],
            publication_id=publication_id,
            total_marks=row["total_marks"],
            percentage=row["percentage"],
            grade=row["grade"],
            gpa=row["gpa"],
            is_pass=row["is_pass"],
            arrear_subjects=row["arrear_subjects"],
            report_card_key=report_key,
            marksheet_key=marksheet_key,
            user=user,
        )
        serialized.append(_serialize_student_result(row, exam_id=exam.pk, publication_id=publication_id))
    return serialized


def _analytics_summary(exam, *, college: bool, tenant) -> dict:
    results, _snapshot = _build_student_results(exam, college=college, tenant=tenant)
    percents = [r["percentage"] for r in results if r["percentage"] is not None]
    absent_count = sum(1 for r in results if not r["is_pass"] and not percents)
    valid = [float(p) for p in percents]
    average = round(sum(valid) / len(valid), 1) if valid else 0
    pass_pct = round(len([p for p in valid if p >= 35]) / len(valid) * 100) if valid else 0

    toppers = sorted(
        [
            {
                "studentId": str(r["student"].student_profile_id),
                "studentName": r["student"].user.full_name,
                "percent": float(r["percentage"]),
            }
            for r in results
            if r["percentage"] is not None
        ],
        key=lambda x: x["percent"],
        reverse=True,
    )[:5]

    bands = [
        ("90–100", 90, 100),
        ("75–89", 75, 89.9),
        ("60–74", 60, 74.9),
        ("35–59", 35, 59.9),
        ("<35", 0, 34.9),
    ]
    breakdown = [
        {"band": label, "count": len([p for p in valid if lo <= p <= hi])}
        for label, lo, hi in bands
    ]
    breakdown.append({"band": "AB", "count": absent_count})

    return {
        "examId": str(exam.pk),
        "generatedAt": timezone.now().isoformat(),
        "passPercent": pass_pct,
        "absentCount": absent_count,
        "averagePercent": average,
        "toppers": toppers,
        "breakdown": breakdown,
    }


@transaction.atomic
def compute_results(exam, *, branch, tenant) -> dict:
    if result_q.count_unsubmitted_marks_for_exam(exam.pk):
        raise ValidationError({"marksStatus": "All marks must be submitted before computing results."})

    college = is_college(tenant)
    results, snapshot_hash = _build_student_results(exam, college=college, tenant=tenant)

    absent_count = sum(1 for r in results if not r["is_pass"] and float(r["percentage"]) == 0)
    valid = [float(r["percentage"]) for r in results]
    average = round(sum(valid) / len(valid), 1) if valid else 0

    token = secrets.token_urlsafe(32)
    now = timezone.now()
    expires_at = now + timedelta(seconds=CONFIRM_TTL_SECONDS)
    summary = {
        "examId": str(exam.pk),
        "totalStudents": len(results),
        "absentCount": absent_count,
        "averagePercent": average,
    }
    cache.set(
        _cache_key(exam.pk),
        {
            "token": token,
            "snapshot_hash": snapshot_hash,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "summary": summary,
        },
        timeout=CONFIRM_TTL_SECONDS,
    )

    result_q.update_exam_publication_state(
        exam,
        is_published=False,
        result_status=ResultStatus.PROVISIONAL,
        user=None,
    )

    return {
        "confirmToken": token,
        "createdAt": now.isoformat(),
        "expiresAt": expires_at.isoformat(),
        "summary": summary,
        "studentResults": [
            _serialize_student_result(r, exam_id=exam.pk) for r in results
        ],
    }


@transaction.atomic
def publish_results(exam, *, branch, tenant, confirm_token: str | None, note: str, user) -> dict:
    if not confirm_token:
        raise ConfirmTokenRequiredError()

    pending = cache.get(_cache_key(exam.pk))
    if not pending or pending.get("token") != confirm_token:
        raise InvalidConfirmTokenError()
    expires_at = pending.get("expires_at")
    if expires_at and timezone.now() > datetime.fromisoformat(expires_at):
        raise InvalidConfirmTokenError(detail="Publish confirmation token has expired.")

    locked = result_q.lock_exam_for_publish(exam.pk)
    if not locked:
        raise ValidationError({"exam": "Exam not found."})
    if locked.publish_in_progress:
        raise PublishJobInProgressError()

    result_q.set_exam_publish_in_progress(locked, True, user=user)
    try:
        college = is_college(tenant)
        results, snapshot_hash = _build_student_results(locked, college=college, tenant=tenant)
        if snapshot_hash != pending.get("snapshot_hash"):
            raise InvalidConfirmTokenError(detail="Marks changed since compute. Re-run compute first.")

        now = timezone.now()
        publication = result_q.create_publication(
            exam_id=locked.pk,
            published_at=now,
            published_by=user,
            snapshot_hash=snapshot_hash,
            revision_no=1,
            user=user,
        )
        student_results = _persist_student_results(
            exam=locked,
            branch=branch,
            institution_name=getattr(tenant, "name", branch.name),
            results=results,
            publication_id=publication.pk,
            college=college,
            user=user,
        )
        result_q.lock_marks_for_exam(locked.pk, user=user)
        result_q.update_exam_publication_state(
            locked,
            is_published=True,
            result_status=ResultStatus.PUBLISHED,
            user=user,
        )
        cache.delete(_cache_key(locked.pk))
        return {
            "publication": {
                "id": str(publication.pk),
                "examId": str(locked.pk),
                "publishedAt": now.isoformat(),
                "publishedByUserId": str(user.pk),
                "revisionNo": publication.revision_no,
                "note": note or "Published",
                "snapshotHash": snapshot_hash,
            },
            "studentResults": student_results,
        }
    finally:
        result_q.set_exam_publish_in_progress(locked, False, user=user)


@transaction.atomic
def revise_results(exam, *, branch, tenant, note: str, user) -> dict:
    current = result_q.get_current_publication(exam.pk)
    if not current:
        raise ValidationError({"result": "No published results to revise."})

    college = is_college(tenant)
    results, snapshot_hash = _build_student_results(exam, college=college, tenant=tenant)
    previous_hash = current.snapshot_hash

    result_q.supersede_publication(current, user=user)
    now = timezone.now()
    publication = result_q.create_publication(
        exam_id=exam.pk,
        published_at=now,
        published_by=user,
        snapshot_hash=snapshot_hash,
        revision_no=current.revision_no + 1,
        parent_publication_id=current.pk,
        user=user,
    )
    student_results = _persist_student_results(
        exam=exam,
        branch=branch,
        institution_name=getattr(tenant, "name", branch.name),
        results=results,
        publication_id=publication.pk,
        college=college,
        user=user,
    )
    result_q.create_revision_history(
        publication_id=publication.pk,
        changed_by=user,
        change_summary=note or "Revised",
        field_changes={"note": note},
        previous_snapshot_hash=previous_hash,
        new_snapshot_hash=snapshot_hash,
        user=user,
    )
    result_q.update_exam_publication_state(
        exam,
        is_published=True,
        result_status=ResultStatus.REVISED,
        user=user,
    )
    return {
        "publication": {
            "id": str(publication.pk),
            "examId": str(exam.pk),
            "publishedAt": now.isoformat(),
            "publishedByUserId": str(user.pk),
            "revisionNo": publication.revision_no,
            "note": note or "Revised",
            "snapshotHash": snapshot_hash,
        },
        "studentResults": student_results,
    }


@transaction.atomic
def apply_grace_marks(exam, *, tenant, entries: list[dict], user) -> dict:
    if not is_college(tenant):
        raise GraceMarksCollegeOnlyError()

    if exam.is_published:
        raise ValidationError({"exam": "Grace marks cannot be changed after results are published."})

    updated = []
    for item in entries:
        # `student_id` is the StudentProfile id (API). Resolve to the enrollment id.
        enrollment = enrollment_q.get_active_enrollment_for_profile(item["student_id"])
        if not enrollment:
            continue
        entry = result_q.apply_grace_to_marks_entry(
            exam_id=exam.pk,
            subject_id=item["subject_id"],
            student_id=enrollment.pk,
            grace_amount=item["grace_marks"],
            user=user,
        )
        if entry:
            updated.append(
                {
                    "studentId": str(entry.student.student_profile_id),
                    "subjectId": str(entry.subject_id),
                    "graceApplied": float(entry.grace_applied),
                }
            )
    return {"updated": updated}


def get_exam_analytics(exam, *, tenant) -> dict:
    college = is_college(tenant)
    return _analytics_summary(exam, college=college, tenant=tenant)


def delete_published_result(publication_id) -> None:
    """EC-EXAM-03 — block hard deletes of published results."""
    raise PublishedResultDeleteError()
