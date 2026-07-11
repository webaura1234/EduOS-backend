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
    """{ student_pk: (percent, total, present_like, excused) } for many students."""
    counts = record_q.aggregate_counts_by_student(
        [sp.pk for sp in students], date_from=date_from, date_to=date_to,
        exclude_exam_days=exclude_exam,
    )
    out = {}
    for sp in students:
        present_like, excused, total = counts.get(sp.pk, (0, 0, 0))
        out[sp.pk] = (attendance_percent(present_like, excused, total), total, present_like, excused)
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
        pct, total, present_like, excused = percents[sp.pk]
        if below_threshold_only:
            if total <= 0 or not is_below_threshold(pct, threshold):
                continue
                
        # Status calculation
        status_label = "Good"
        if total > 0:
            if is_below_threshold(pct, threshold):
                status_label = "Shortage"
            elif is_below_threshold(pct, threshold + 5):
                status_label = "Warning"
                
        present_days = present_like + excused
        absent_days = total - present_days

        # Safe attribute access since we select_related batch, course, academic_year
        class_name = sp.batch.course.name if sp.batch_id and sp.batch.course_id else ""
        section_name = sp.batch.name if sp.batch_id else ""
        academic_year = sp.batch.academic_year.name if sp.batch_id and getattr(sp.batch, 'academic_year_id', None) else ""
        admission_no = sp.student_profile.admission_number if sp.student_profile_id else ""

        rows.append({
            "studentId": str(sp.student_profile_id), # Keep for internal use if needed
            "admissionNo": admission_no,
            "name": sp.user.full_name,
            "class": class_name,
            "section": section_name,
            "academicYear": academic_year,
            "batchId": str(sp.current_batch_id) if sp.current_batch_id else None,
            "percent": pct,
            "sessions": total,
            "present": present_days,
            "absent": absent_days,
            "status": status_label,
            "branchName": branch.name,
        })
    rows.sort(key=lambda r: r["percent"])
    return {
        "threshold": threshold,
        "dateFrom": date_from.isoformat(),
        "dateTo": date_to.isoformat(),
        "rows": rows,
    }


def branch_attendance_summary(branches, *, date_from=_WIDE_FROM, date_to=_WIDE_TO) -> dict:
    """Per-branch student-attendance rollup from ONE grouped aggregate scan:
    ``{branch_pk: {"percent": avg%, "lowAttendanceCount": n_below_threshold}}``.

    Both values derive from the same per-student counts, so the super-admin dashboard
    needs neither a per-branch ``ranking_report`` NOR a per-branch ``shortage_report``
    (each of which was its own full-range scan per branch):
      - ``percent`` == averaging ``ranking_report(branch)["rows"][*]["percent"]`` per branch.
      - ``lowAttendanceCount`` == ``len(shortage_report(branch)["rows"])`` at the tenant
        threshold — a student counts when it has records AND is below threshold.

    Exam-day handling and the threshold are tenant-level, so they're read once (all
    branches in a super-admin rollup share a tenant).
    """
    branches = list(branches)
    if not branches:
        return {}

    threshold, exam_counts = roster_q.attendance_config(branches[0])
    exclude_exam = not exam_counts

    students_by_branch = {}
    all_ids = []
    for b in branches:
        students = _students_for_report(b)
        students_by_branch[b.pk] = students
        all_ids.extend(sp.pk for sp in students)

    counts = (
        record_q.aggregate_counts_by_student(
            all_ids, date_from=date_from, date_to=date_to, exclude_exam_days=exclude_exam
        )
        if all_ids
        else {}
    )

    result = {}
    for b in branches:
        students = students_by_branch[b.pk]
        if not students:
            result[b.pk] = {"percent": 0, "lowAttendanceCount": 0}
            continue
        percents = []
        low = 0
        for sp in students:
            pct = attendance_percent(*counts.get(sp.pk, (0, 0, 0)))
            _pl, _ex, total = counts.get(sp.pk, (0, 0, 0))
            percents.append(pct)
            if total > 0 and is_below_threshold(pct, threshold):
                low += 1
        result[b.pk] = {
            "percent": round(sum(percents) / len(percents)),
            "lowAttendanceCount": low,
        }
    return result


def branch_average_attendance_percents(branches, *, date_from=_WIDE_FROM, date_to=_WIDE_TO) -> dict:
    """Backwards-compatible ``{branch_pk: percent}`` view over ``branch_attendance_summary``."""
    return {
        pk: s["percent"]
        for pk, s in branch_attendance_summary(
            branches, date_from=date_from, date_to=date_to
        ).items()
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
