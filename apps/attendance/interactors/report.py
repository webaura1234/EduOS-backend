"""Interactors — attendance % engine: summaries, shortage/detention, monthly reports.

Implements EC-ATT-05 (exam-day exclusion when the tenant setting is off).
The % math is in helpers; all DB reads go through queries.
"""

import datetime

from apps.academics.queries import curriculum as curr_q
from apps.attendance.helpers import attendance_percent, is_below_threshold, month_bounds
from apps.attendance.queries import record as record_q
from apps.attendance.queries import roster as roster_q

_WIDE_FROM = datetime.date(1970, 1, 1)
_WIDE_TO = datetime.date(2999, 12, 31)


def _percent(student_id, *, date_from, date_to, exclude_exam, batch_subject_id=None):
    present_like, excused, total = record_q.aggregate_counts(
        student_id, date_from=date_from, date_to=date_to,
        exclude_exam_days=exclude_exam, batch_subject_id=batch_subject_id,
    )
    return attendance_percent(present_like, excused, total), total


def _percent_map(students, *, date_from, date_to, exclude_exam):
    """{ student_pk: (percent, total) } for many students in a single query (no N+1)."""
    counts = record_q.aggregate_counts_by_student(
        [sp.pk for sp in students], date_from=date_from, date_to=date_to,
        exclude_exam_days=exclude_exam,
    )
    out = {}
    for sp in students:
        present_like, excused, total = counts.get(sp.pk, (0, 0, 0))
        out[sp.pk] = (attendance_percent(present_like, excused, total), total)
    return out


def _students_for_report(branch, batch_id=None):
    if batch_id:
        return list(roster_q.students_in_batch(batch_id))
    return list(roster_q.all_active_students_in_branch(branch.pk))


def _attendance_rows(
    branch,
    *,
    date_from,
    date_to,
    batch_id=None,
    threshold=None,
    below_threshold_only=False,
) -> dict:
    cfg_threshold, exam_counts = roster_q.attendance_config(branch)
    threshold = threshold if threshold is not None else cfg_threshold
    exclude_exam = not exam_counts

    students = _students_for_report(branch, batch_id)
    percents = _percent_map(students, date_from=date_from, date_to=date_to, exclude_exam=exclude_exam)

    rows = []
    for sp in students:
        pct, total = percents[sp.pk]
        if below_threshold_only:
            if total <= 0 or not is_below_threshold(pct, threshold):
                continue
        rows.append({
            "studentId": str(sp.student_profile_id),
            "name": sp.user.full_name,
            "batchId": str(sp.current_batch_id) if sp.current_batch_id else None,
            "percent": pct,
            "sessions": total,
        })
    rows.sort(key=lambda r: r["percent"])
    return {
        "threshold": threshold,
        "dateFrom": date_from.isoformat(),
        "dateTo": date_to.isoformat(),
        "rows": rows,
    }


def student_summary(branch, student, *, date_from=_WIDE_FROM, date_to=_WIDE_TO) -> dict:
    """Overall + subject-wise % for one student (F-111/112)."""
    threshold, exam_counts = roster_q.attendance_config(branch)
    exclude_exam = not exam_counts

    overall_pct, overall_total = _percent(
        student.pk, date_from=date_from, date_to=date_to, exclude_exam=exclude_exam
    )

    subjects = []
    if student.current_batch_id:
        for bs in curr_q.list_batch_subjects(branch.pk, batch_id=student.current_batch_id):
            pct, total = _percent(
                student.pk, date_from=date_from, date_to=date_to,
                exclude_exam=exclude_exam, batch_subject_id=bs.pk,
            )
            subjects.append({
                "batchSubjectId": str(bs.pk),
                "subjectId": str(bs.subject_id),
                "subjectName": bs.subject.name,
                "percent": pct,
                "sessions": total,
                "belowThreshold": is_below_threshold(pct, threshold) and total > 0,
            })

    return {
        "studentId": str(student.student_profile_id),
        "overallPercent": overall_pct,
        "totalSessions": overall_total,
        "threshold": threshold,
        "belowThreshold": is_below_threshold(overall_pct, threshold) and overall_total > 0,
        "subjects": subjects,
    }


def ranking_report(branch, *, date_from, date_to, batch_id=None) -> dict:
    """All students ranked by attendance % for a date range (admin shortage table)."""
    return _attendance_rows(
        branch, date_from=date_from, date_to=date_to, batch_id=batch_id, below_threshold_only=False
    )


def shortage_report(
    branch,
    *,
    threshold=None,
    batch_id=None,
    date_from=None,
    date_to=None,
) -> dict:
    """Students below the attendance threshold (F-105/114/115)."""
    date_from = date_from or _WIDE_FROM
    date_to = date_to or _WIDE_TO
    return _attendance_rows(
        branch,
        date_from=date_from,
        date_to=date_to,
        batch_id=batch_id,
        threshold=threshold,
        below_threshold_only=True,
    )


def detention_report(
    branch,
    *,
    batch_id=None,
    date_from=None,
    date_to=None,
) -> dict:
    """Auto-generated detention list = shortage at the configured threshold (F-115)."""
    return shortage_report(branch, batch_id=batch_id, date_from=date_from, date_to=date_to)


def monthly_report(branch, *, year, month, batch_id=None) -> dict:
    """Per-student attendance % for one month (F-110)."""
    date_from, date_to = month_bounds(year, month)
    report = ranking_report(branch, date_from=date_from, date_to=date_to, batch_id=batch_id)
    report["year"] = year
    report["month"] = month
    return report
