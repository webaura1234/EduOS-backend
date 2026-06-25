"""
Seed a single school tenant — CMR Lalgadi — with one user of each role,
classes 1-7 (each with a Section A), an enrolled student, a linked parent,
and supporting mock data (Class-5 subjects, syllabus units, an announcement,
a fee invoice, and an attendance record).

Idempotent — safe to run repeatedly. Run with:

    python seed_cmr.py            # uses config.settings.dev (your configured DB)

All users share the password below.
"""

import datetime
import os
import sys

import django
from django.conf import settings as dj_settings

if not dj_settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()

from django.core.management import call_command  # noqa: E402
from django.utils import timezone  # noqa: E402

from apps.academics.models import (  # noqa: E402
    AcademicYear, Batch, BatchFaculty, BatchSubject, Course, Department,
    Room, Subject, SyllabusUnit, SyllabusUnitProgress,
)
from apps.academics.models.calendar import AcademicPeriod, PeriodType  # noqa: E402
from apps.academics.models.timetable import (  # noqa: E402
    PeriodSlot, Timetable, TimetableEntry,
)
from apps.accounts.models.guardian import StudentGuardianLink  # noqa: E402
from apps.accounts.models.profile import GuardianProfile, StudentProfile  # noqa: E402
from apps.accounts.models.user import Role, User  # noqa: E402
from apps.admissions.models.enrollment import StudentEnrollment  # noqa: E402
from apps.attendance.models.record import AttendanceRecord  # noqa: E402
from apps.attendance.models.session import AttendanceSession  # noqa: E402
from apps.communications.models.announcement import Announcement  # noqa: E402
from apps.coursework.models import Homework  # noqa: E402
from apps.examinations.models import Exam, ExamScheduleSlot, MarksEntry  # noqa: E402
from apps.fees.models.invoice import FeeInvoice, FeeInvoiceLine  # noqa: E402
from apps.fees.helpers.paise import financial_year_for  # noqa: E402
from apps.hr.models import Employee, LeaveBalance, StaffAttendance  # noqa: E402
from apps.organizations.models import (  # noqa: E402
    Branch, PlanSubscription, Tenant, TenantQuota, TenantSettings,
)

PASSWORD = "Password123!"
SUBDOMAIN = "greenfield"
SCHOOL_NAME = "CMR Lalgadi"
CITY, STATE = "Hyderabad", "Telangana"

# Phone logins
SUPER_ADMIN_PHONE = "+919876543200"
ADMIN_PHONE = "+919876543210"
PARENT_PHONE = "+919876543220"

_PLAN = dict(student_limit=500, storage_limit_gb=10, sms_quota_per_month=1000,
             ai_token_quota_per_month=10000, api_rpm_limit=100)


def _set_password(user: User) -> None:
    if not user.has_usable_password() or not user.check_password(PASSWORD):
        user.set_password(PASSWORD)
        user.save(update_fields=["password"])


def _user(*, role, tenant, branch, first_name, last_name, phone=None, login_id=None) -> User:
    lookup = {"role": role, "tenant": tenant}
    if login_id:
        lookup["custom_login_id"] = login_id
    else:
        lookup["phone"] = phone
    user, created = User.objects.get_or_create(
        **lookup,
        defaults=dict(first_name=first_name, last_name=last_name, branch=branch,
                      phone=phone, custom_login_id=login_id,
                      must_change_password=False, is_active=True),
    )
    _set_password(user)
    print(f"  - {role:<13} {login_id or phone:<16} [{'created' if created else 'exists'}]")
    return user


def reset_data():
    """Remove ALL existing rows from every table (keeps schema). Destructive."""
    print("Wiping all existing data (manage.py flush)...")
    call_command("flush", "--no-input")
    print("  - database emptied.\n")


def seed():
    print(f"\nSeeding {SCHOOL_NAME} ({SUBDOMAIN}.eduos.app)\n")

    # ── Tenant + branch + settings + plan + quotas ──────────────────────────
    tenant, _ = Tenant.objects.get_or_create(
        subdomain=SUBDOMAIN,
        defaults=dict(name=SCHOOL_NAME, institution_type="school", status="active",
                      city=CITY, state=STATE, parent_access_enabled=True),
    )
    branch, _ = Branch.objects.get_or_create(
        tenant=tenant, name="Main Campus",
        defaults=dict(code="MC", is_primary=True, city=CITY, state=STATE),
    )
    TenantSettings.objects.get_or_create(
        tenant=tenant,
        defaults=dict(student_id_label="Roll Number", faculty_id_label="Employee ID",
                      attendance_mode="day"),  # schools mark once per student per day
    )
    PlanSubscription.objects.get_or_create(
        tenant=tenant, defaults=dict(plan="starter", billing_status="trial", **_PLAN),
    )
    for resource, hard in (("students", _PLAN["student_limit"]),
                           ("sms_count", _PLAN["sms_quota_per_month"]),
                           ("ai_tokens", _PLAN["ai_token_quota_per_month"])):
        TenantQuota.objects.get_or_create(
            tenant=tenant, resource=resource,
            period_start=datetime.date.today().replace(day=1),
            defaults=dict(period="month", usage=0, soft_cap=int(hard * 0.9), hard_cap=hard),
        )

    # ── Users (one of each role) ────────────────────────────────────────────
    print("Users:")
    _user(role=Role.SUPER_ADMIN, tenant=tenant, branch=None,
          first_name="Ravi", last_name="SuperAdmin", phone=SUPER_ADMIN_PHONE)
    _user(role=Role.ADMIN, tenant=tenant, branch=branch,
          first_name="Anita", last_name="Admin", phone=ADMIN_PHONE)
    faculty = _user(role=Role.FACULTY, tenant=tenant, branch=branch,
                    first_name="Priya", last_name="Patel", login_id="FAC-001")
    student_user = _user(role=Role.STUDENT, tenant=tenant, branch=branch,
                         first_name="Rahul", last_name="Sharma", login_id="STU-001")
    parent_user = _user(role=Role.PARENT, tenant=tenant, branch=branch,
                        first_name="Suresh", last_name="Sharma", phone=PARENT_PHONE)

    # ── Academic year + department + classes 1-7 (Section A each) ───────────
    print("\nAcademic structure:")
    year, _ = AcademicYear.objects.get_or_create(
        branch=branch, name="2025-2026",
        defaults=dict(start_date=datetime.date(2025, 6, 1),
                      end_date=datetime.date(2026, 4, 30), is_current=True),
    )
    period, _ = AcademicPeriod.objects.get_or_create(
        academic_year=year, sequence=1,
        defaults=dict(period_type=PeriodType.TERM, name="Term 1",
                      start_date=year.start_date, end_date=year.end_date),
    )
    dept, _ = Department.objects.get_or_create(
        branch=branch, code="PRI", defaults=dict(name="Primary School"),
    )
    class5_batch = None
    for n in range(1, 8):
        course, _ = Course.objects.get_or_create(
            department=dept, code=f"C{n}", defaults=dict(name=f"Class {n}"),
        )
        batch, _ = Batch.objects.get_or_create(
            course=course, academic_year=year, name="A",
            defaults=dict(capacity=40),
        )
        print(f"  - Class {n} → Section A")
        if n == 5:
            class5_batch = batch

    # Faculty is class teacher of Class 5 - A
    if class5_batch.class_teacher_id != faculty.pk:
        class5_batch.class_teacher = faculty
        class5_batch.save(update_fields=["class_teacher"])

    # ── Student profile + active enrollment in Class 5 - A ──────────────────
    print("\nStudent + parent:")
    profile, _ = StudentProfile.objects.get_or_create(
        user=student_user,
        defaults=dict(gender="male", date_of_birth=datetime.date(2015, 3, 12),
                      admission_date=datetime.date(2025, 6, 1),
                      current_batch=class5_batch),
    )
    if profile.current_batch_id != class5_batch.pk:
        profile.current_batch = class5_batch
        profile.save(update_fields=["current_batch"])

    enrollment, _ = StudentEnrollment.objects.get_or_create(
        student_profile=profile, academic_year=year,
        defaults=dict(branch=branch, batch=class5_batch, status="active"),
    )
    if profile.current_enrollment_id != enrollment.pk:
        profile.current_enrollment = enrollment
        profile.save(update_fields=["current_enrollment"])
    print(f"  - Rahul Sharma enrolled in Class 5 - A")

    # ── Parent guardian profile + link ──────────────────────────────────────
    GuardianProfile.objects.get_or_create(
        user=parent_user, defaults=dict(relationship_default="father", occupation="Engineer"),
    )
    StudentGuardianLink.objects.get_or_create(
        student=student_user, guardian=parent_user,
        defaults=dict(relationship="father", is_primary_contact=True, has_portal_access=True),
    )
    print(f"  - Suresh Sharma linked as father (primary contact)")

    # ── Faculty employee record + leave balances ────────────────────────────
    employee, _ = Employee.objects.get_or_create(
        user=faculty, defaults=dict(branch=branch, employee_code="EMP-001",
                                    employment_type="full_time", designation="Teacher",
                                    joined_at=datetime.date(2024, 6, 1)),
    )
    fy = financial_year_for(datetime.date.today())
    for leave_type, days in (("casual", 12), ("sick", 10), ("earned", 15)):
        LeaveBalance.objects.get_or_create(
            employee=employee, leave_type=leave_type, year=fy,
            defaults=dict(balance_days=days),
        )
    print(f"  - Faculty leave balances seeded for {fy} (casual 12, sick 10, earned 15)")

    # ── Faculty self-attendance: present on this month's working days so far ─
    working = set(branch.working_days or [1, 2, 3, 4, 5, 6])
    today_d = datetime.date.today()
    present_days = 0
    for day in range(1, today_d.day + 1):
        d = datetime.date(today_d.year, today_d.month, day)
        if (d.isoweekday() % 7) in working:
            StaffAttendance.objects.get_or_create(
                user=faculty, date=d,
                defaults=dict(branch=branch, status="present", marked_at=timezone.now(),
                              created_by=faculty, updated_by=faculty),
            )
            present_days += 1
    print(f"  - Faculty marked present on {present_days} working day(s) this month")

    # ── Class-5 subjects + faculty assignment + syllabus units ──────────────
    print("\nSubjects + syllabus:")
    class5_course = class5_batch.course
    subjects = {}
    batch_subjects = {}
    for name, code in (("English", "ENG5"), ("Mathematics", "MAT5"), ("Science", "SCI5")):
        subj, _ = Subject.objects.get_or_create(
            course=class5_course, code=code, defaults=dict(name=name),
        )
        subjects[name] = subj
        bs, _ = BatchSubject.objects.get_or_create(
            batch=class5_batch, subject=subj, academic_period=period,
        )
        batch_subjects[name] = bs
        BatchFaculty.objects.get_or_create(
            batch_subject=bs, faculty=faculty,
            defaults=dict(role="primary", assigned_at=datetime.date(2025, 6, 1)),
        )
        print(f"  - {name} (taught by Priya Patel)")

    for i, title in enumerate(["Numbers & Place Value", "Addition & Subtraction",
                               "Multiplication", "Fractions"], start=1):
        SyllabusUnit.objects.get_or_create(
            branch=branch, subject=subjects["Mathematics"], title=title,
            defaults=dict(order=i),
        )
    for i, title in enumerate(["Reading comprehension", "Grammar", "Writing"], start=1):
        SyllabusUnit.objects.get_or_create(
            branch=branch, subject=subjects["English"], title=title,
            defaults=dict(order=i),
        )
    for i, title in enumerate(["Plants", "Animals", "Matter"], start=1):
        SyllabusUnit.objects.get_or_create(
            branch=branch, subject=subjects["Science"], title=title,
            defaults=dict(order=i),
        )
    print("  - Syllabus units on Mathematics, English, Science")

    math_units = list(SyllabusUnit.objects.filter(
        branch=branch, subject=subjects["Mathematics"], is_active=True,
    ).order_by("order")[:2])
    for unit in math_units:
        SyllabusUnitProgress.objects.get_or_create(
            branch=branch, batch=class5_batch, unit=unit,
            defaults=dict(completed_at=timezone.now(), completed_by=faculty),
        )
    if math_units:
        print(f"  - Class 5-A Mathematics: {len(math_units)}/4 units marked complete (sample)")

    # ── Homework for Class 5-A (published) ──────────────────────────────────
    print("\nHomework:")
    hw_plan = [
        ("Mathematics", "Fractions worksheet", "Complete exercises 1-10 on page 45."),
        ("English", "Essay: My favourite season", "Write 150 words; submit tomorrow."),
        ("Science", "Read chapter 6", "Read 'Plants and Photosynthesis' and note 5 key points."),
    ]
    for i, (subj, title, details) in enumerate(hw_plan):
        Homework.objects.get_or_create(
            branch=branch, batch=class5_batch, title=title,
            defaults=dict(date=datetime.date.today() - datetime.timedelta(days=i),
                          details=details, status="published", published_at=timezone.now(),
                          created_by=faculty, updated_by=faculty),
        )
    print(f"  - {len(hw_plan)} homework items for Class 5 - A")

    # ── Announcement ────────────────────────────────────────────────────────
    Announcement.objects.get_or_create(
        branch=branch, title="Welcome to the new academic year!",
        defaults=dict(body="School reopens on June 1. Please check your timetable.",
                      created_by=faculty),
    )
    print("\n  - 1 announcement created")

    # ── Fee invoice for the student ─────────────────────────────────────────
    invoice, created_inv = FeeInvoice.objects.get_or_create(
        student=enrollment, branch=branch,
        defaults=dict(due_date=datetime.date(2025, 7, 31),
                      total_paise=5000000, paid_paise=0, status="due"),
    )
    if created_inv:
        FeeInvoiceLine.objects.create(invoice=invoice, label="Tuition Fee (Term 1)",
                                      amount_paise=5000000)
    print("  - 1 fee invoice (₹50,000 due)")

    # ── Timetable: Maths for Class 5-A every weekday (Mon-Fri), Period 1 ─────
    print("\nTimetable + attendance:")
    slot, _ = PeriodSlot.objects.get_or_create(
        branch=branch, sequence=1,
        defaults=dict(name="Period 1", start_time=datetime.time(9, 0),
                      end_time=datetime.time(9, 45)),
    )
    timetable, _ = Timetable.objects.get_or_create(
        batch=class5_batch, academic_period=period,
        defaults=dict(is_published=True),
    )
    maths_bs = batch_subjects["Mathematics"]
    for day in range(1, 6):  # Mon(1) … Fri(5) — faculty always has a class on weekdays
        TimetableEntry.objects.get_or_create(
            timetable=timetable, batch_subject=maths_bs, period_slot=slot, day_of_week=day,
            defaults=dict(faculty=faculty, status="active"),
        )
    print("  - Maths timetabled Mon-Fri, Period 1 (Priya Patel)")

    # ── Attendance history: last 10 weekday DAY sessions, mostly present ────
    present_count = 0
    total_count = 0
    d = datetime.date.today()
    while total_count < 10:
        if d.isoweekday() <= 5:  # weekday
            sess, _ = AttendanceSession.objects.get_or_create(
                branch=branch, batch=class5_batch, mode="day", date=d,
                defaults=dict(faculty=faculty, status="completed"),
            )
            # Mark every 5th session absent so the percentage is realistic (~80%).
            status = "absent" if total_count % 5 == 4 else "present"
            AttendanceRecord.objects.get_or_create(
                session=sess, student=enrollment,
                # Key MUST match interactor upsert_record ("{session}:{student}") so a later
                # mark updates this row instead of trying to insert a duplicate.
                defaults=dict(status=status, marked_at=timezone.now(), marked_by=faculty,
                              idempotency_key=f"{sess.pk}:{enrollment.pk}"),
            )
            present_count += 1 if status == "present" else 0
            total_count += 1
        d -= datetime.timedelta(days=1)
    print(f"  - {total_count} completed sessions, {present_count} present "
          f"({round(present_count / total_count * 100)}% attendance)")

    # ── Published exams + marks (drives Results + Performance trend) ─────────
    print("\nExams + results:")
    room, _ = Room.objects.get_or_create(branch=branch, name="Room 101",
                                          defaults=dict(capacity=40))
    # Three exams over time with rising marks so the trend chart is meaningful.
    exam_plan = [
        ("Unit Test 1", datetime.date(2025, 8, 10), 0),
        ("Mid-Term", datetime.date(2025, 11, 5), 6),
        ("Unit Test 2", datetime.date(2026, 2, 18), 12),
    ]
    base_marks = {"English": 70, "Mathematics": 72, "Science": 66}
    for exam_name, exam_date, bump in exam_plan:
        exam, _ = Exam.objects.get_or_create(
            branch=branch, academic_period=period, name=exam_name,
            defaults=dict(exam_type="internal", exam_fee_paise=0, is_published=True,
                          marks_deadline=timezone.make_aware(
                              datetime.datetime.combine(exam_date, datetime.time(17, 0)))),
        )
        if not exam.is_published:
            exam.is_published = True
            exam.save(update_fields=["is_published"])
        for subj_name, subj in subjects.items():
            slot, _ = ExamScheduleSlot.objects.get_or_create(
                exam=exam, subject=subj, batch=class5_batch,
                defaults=dict(room=room, max_marks=100,
                              start_at=timezone.make_aware(
                                  datetime.datetime.combine(exam_date, datetime.time(9, 0))),
                              end_at=timezone.make_aware(
                                  datetime.datetime.combine(exam_date, datetime.time(11, 0)))),
            )
            MarksEntry.objects.get_or_create(
                exam=exam, subject=subj, student=enrollment,
                defaults=dict(marks=min(base_marks[subj_name] + bump, 100),
                              marks_status="locked", is_absent=False),
            )
        print(f"  - {exam_name} published (Eng/Maths/Sci marked)")

    print("\n" + "=" * 52)
    print(f"Done. Login at {SUBDOMAIN}.<your-domain>")
    print(f"All passwords: {PASSWORD}")
    print("  Super Admin :", SUPER_ADMIN_PHONE)
    print("  Admin       :", ADMIN_PHONE)
    print("  Faculty     : FAC-001")
    print("  Student     : STU-001")
    print("  Parent      :", PARENT_PHONE)
    print("=" * 52)


if __name__ == "__main__":
    # By default this WIPES the database first, then seeds. Pass --no-flush to
    # seed without wiping (idempotent top-up).
    if "--no-flush" not in sys.argv:
        if "--yes" not in sys.argv and sys.stdin.isatty():
            ans = input(
                f"This will DELETE ALL DATA in the '{dj_settings.DATABASES['default'].get('NAME')}' "
                "database, then seed. Type 'yes' to continue: "
            )
            if ans.strip().lower() != "yes":
                print("Aborted.")
                sys.exit(1)
        reset_data()
    seed()
