"""Equivalence lock: `branch_average_attendance_percents` (batched, one aggregate scan)
must return the exact same per-branch value as averaging `ranking_report(branch)` rows
per branch — the computation the super-admin dashboard used to run per branch.
"""

import datetime

import pytest

from apps.academics.models import (
    AcademicPeriod,
    AcademicYear,
    Batch,
    BatchSubject,
    Course,
    Department,
    PeriodSlot,
    Subject,
)
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.admissions.models import StudentEnrollment
from apps.attendance.enums import SessionStatus
from apps.attendance.interactors import report as report_i
from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.organizations.models import TenantSettings
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db

WIDE_FROM = datetime.date(1970, 1, 1)
WIDE_TO = datetime.date(2999, 12, 31)


def _make_branch(tenant, label, student_status_lists):
    """Create a branch whose students have the given per-session attendance statuses.

    ``student_status_lists`` is a list (one entry per student) of status lists; an empty
    list means an enrolled student with no attendance records.
    """
    branch = BranchFactory(tenant=tenant)
    year = AcademicYear.objects.create(
        branch=branch, name="2024-25", is_current=True,
        start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2025, 4, 30),
    )
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type="term", sequence=1, name="T1",
        start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2024, 10, 31),
    )
    dept = Department.objects.create(branch=branch, name="Sci", department_type="stream")
    course = Course.objects.create(department=dept, name="G9")
    batch = Batch.objects.create(course=course, academic_year=year, name="A")
    subject = Subject.objects.create(course=course, name="Maths", code=f"MTH-{label}")
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot = PeriodSlot.objects.create(
        branch=branch, name="P1", sequence=1,
        start_time=datetime.time(9, 0), end_time=datetime.time(9, 45),
    )

    enrollments = []
    for i, statuses in enumerate(student_status_lists):
        user = UserFactory(
            role=Role.STUDENT, tenant=tenant, branch=branch,
            custom_login_id=f"STU-{label}-{i}", must_change_password=False,
        )
        profile = StudentProfile.objects.create(
            user=user, current_batch=batch, academic_status=AcademicStatus.ACTIVE
        )
        enr = StudentEnrollment.objects.create(
            branch=branch, student_profile=profile, batch=batch, academic_year=year
        )
        enrollments.append((enr, statuses))

    n_sessions = max((len(s) for _, s in enrollments), default=0)
    sessions = [
        AttendanceSession.objects.create(
            branch=branch, batch=batch, batch_subject=bs, period_slot=slot,
            date=datetime.date(2024, 7, d + 1), status=SessionStatus.COMPLETED,
        )
        for d in range(n_sessions)
    ]
    for enr, statuses in enrollments:
        for d, status in enumerate(statuses):
            AttendanceRecord.objects.create(
                session=sessions[d], student=enr, status=status,
                marked_at=datetime.datetime.now(), idempotency_key=f"{sessions[d].id}:{enr.id}",
            )
    return branch


def _old_avg(branch):
    rows = report_i.ranking_report(branch, date_from=WIDE_FROM, date_to=WIDE_TO)["rows"]
    return round(sum(r["percent"] for r in rows) / len(rows)) if rows else 0


def test_branch_average_matches_per_branch_ranking_report():
    tenant = TenantFactory(institution_type="school")
    TenantSettings.objects.create(
        tenant=tenant, attendance_threshold_percent=75, exam_day_counts_toward_attendance=True
    )

    branch_a = _make_branch(
        tenant, "A", [["present", "present", "absent"], ["present", "present", "present"]]
    )
    branch_b = _make_branch(tenant, "B", [["present", "absent"], []])  # incl. a no-record student
    branch_empty = BranchFactory(tenant=tenant)  # no students at all

    batched = report_i.branch_average_attendance_percents([branch_a, branch_b, branch_empty])

    # Identical to the old per-branch ranking_report average, keyed to the right branch.
    assert batched[branch_a.pk] == _old_avg(branch_a)
    assert batched[branch_b.pk] == _old_avg(branch_b)
    assert batched[branch_empty.pk] == _old_avg(branch_empty) == 0
    # Sanity: real (non-trivial) values, not accidentally all zero.
    assert batched[branch_a.pk] > 0
    assert batched[branch_b.pk] > 0


def test_branch_summary_low_attendance_matches_shortage_report():
    """`branch_attendance_summary` low count == `len(shortage_report(branch)["rows"])`,
    so the super-admin dashboard no longer needs a per-branch shortage_report scan.
    """
    tenant = TenantFactory(institution_type="school")
    TenantSettings.objects.create(
        tenant=tenant, attendance_threshold_percent=75, exam_day_counts_toward_attendance=True
    )
    # A: 67% (below) + 100% (above) → 1 below. B: 50% (below) + no-record (excluded) → 1 below.
    branch_a = _make_branch(
        tenant, "A", [["present", "present", "absent"], ["present", "present", "present"]]
    )
    branch_b = _make_branch(tenant, "B", [["present", "absent"], []])

    summary = report_i.branch_attendance_summary([branch_a, branch_b])

    assert (
        summary[branch_a.pk]["lowAttendanceCount"]
        == len(report_i.shortage_report(branch_a)["rows"])
        == 1
    )
    assert (
        summary[branch_b.pk]["lowAttendanceCount"]
        == len(report_i.shortage_report(branch_b)["rows"])
        == 1
    )
    # Percent stays equivalent to the old ranking-report average too.
    assert summary[branch_a.pk]["percent"] == _old_avg(branch_a)
