"""
Seed CMR Lalgadi (greenfield school tenant) with 3 branches:
each branch has 3 admins, 5 faculty (subjects + class teachers Class 1–5 A),
and 25 students (5 per class). Main Campus keeps rich demo content.

Idempotent — safe to run repeatedly. Run with:

    python seed_cmr.py            # flush + seed (destructive)
    python seed_cmr.py --no-flush # top-up without wiping

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
from apps.academics.models.admin_extras import StudyMaterial, StudyMaterialFolder  # noqa: E402
from apps.academics.models.calendar import AcademicPeriod, PeriodType  # noqa: E402
from apps.academics.models.timetable import (  # noqa: E402
    PeriodSlot, Timetable, TimetableEntry,
)
from apps.accounts.models.guardian import StudentGuardianLink  # noqa: E402
from apps.accounts.models.profile import FacultyProfile, GuardianProfile, StudentProfile  # noqa: E402
from apps.accounts.models.user import Role, User  # noqa: E402
from apps.admissions.models.enrollment import StudentEnrollment  # noqa: E402
from apps.attendance.models.record import AttendanceRecord  # noqa: E402
from apps.attendance.models.session import AttendanceSession  # noqa: E402
from apps.communications.models.announcement import Announcement, AnnouncementTargetType  # noqa: E402
from apps.coursework.models import Homework  # noqa: E402
from apps.examinations.enums import MarksStatus  # noqa: E402
from apps.examinations.interactors.result import compute_results, publish_results  # noqa: E402
from apps.examinations.models import Exam, ExamScheduleSlot, MarksEntry  # noqa: E402
from apps.fees.models.invoice import FeeInvoice, FeeInvoiceLine  # noqa: E402
from apps.fees.helpers.paise import financial_year_for  # noqa: E402
from apps.grievances.models import Grievance, GrievanceRaiserRole, GrievanceStatus  # noqa: E402
from apps.hr.enums import PayrollRunStatus  # noqa: E402
from apps.hr.models import Employee, LeaveBalance, Payslip, PayrollRun, StaffAttendance  # noqa: E402
from apps.organizations.models import (  # noqa: E402
    Branch, PlanSubscription, Tenant, TenantQuota, TenantSettings,
)

PASSWORD = "Password123!"
SUBDOMAIN = "greenfield"
SCHOOL_NAME = "CMR Lalgadi"
CITY, STATE = "Hyderabad", "Telangana"

SUPER_ADMIN_PHONE = "+919876543200"
ADMIN_PHONE = "+919876543210"
PARENT_PHONE = "+919876543220"
PARENT2_PHONE = "+919876543221"

_PLAN = dict(
    student_limit=500,
    storage_limit_gb=10,
    sms_quota_per_month=1000,
    ai_token_quota_per_month=10000,
    api_rpm_limit=100,
)

PAYROLL_COMPONENTS = [
    {"name": "Basic", "kind": "earning", "calc": "fixed", "amountPaise": 3_000_000},
    {"name": "HRA", "kind": "earning", "calc": "percent_of_basic", "percent": 40},
    {"name": "PF", "kind": "deduction", "calc": "fixed", "amountPaise": 180_000},
]
PAYROLL_NET = 4_020_000

BRANCH_SPECS = (
    dict(name="Main Campus", code="MC", is_primary=True, rich=True),
    dict(name="North Campus", code="NC", is_primary=False, rich=False),
    dict(name="South Campus", code="SC", is_primary=False, rich=False),
)

SUBJECT_SPECS = (
    ("Mathematics", "MAT"),
    ("English", "ENG"),
    ("Science", "SCI"),
    ("Social Studies", "SST"),
    ("Hindi", "HIN"),
)


def _days_ago(n: int) -> datetime.date:
    return datetime.date.today() - datetime.timedelta(days=n)


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
        defaults=dict(
            first_name=first_name,
            last_name=last_name,
            branch=branch,
            phone=phone,
            custom_login_id=login_id,
            must_change_password=False,
            is_active=True,
        ),
    )
    _set_password(user)
    print(f"  - {role:<13} {login_id or phone:<16} [{'created' if created else 'exists'}]")
    return user


def _enroll_student(*, user, branch, batch, year, dob, gender="male") -> StudentEnrollment:
    profile, _ = StudentProfile.objects.get_or_create(
        user=user,
        defaults=dict(
            gender=gender,
            date_of_birth=dob,
            admission_date=datetime.date(2025, 6, 1),
            current_batch=batch,
        ),
    )
    if profile.current_batch_id != batch.pk:
        profile.current_batch = batch
        profile.save(update_fields=["current_batch"])

    enrollment, _ = StudentEnrollment.objects.get_or_create(
        student_profile=profile,
        academic_year=year,
        defaults=dict(branch=branch, batch=batch, status="active"),
    )
    if profile.current_enrollment_id != enrollment.pk:
        profile.current_enrollment = enrollment
        profile.save(update_fields=["current_enrollment"])
    return enrollment


def _link_parent(*, student, guardian, relationship="father") -> None:
    GuardianProfile.objects.get_or_create(
        user=guardian,
        defaults=dict(relationship_default=relationship, occupation="Professional"),
    )
    StudentGuardianLink.objects.get_or_create(
        student=student,
        guardian=guardian,
        defaults=dict(relationship=relationship, is_primary_contact=True, has_portal_access=True),
    )


def _publish_exam_results(exam, *, branch, tenant, admin) -> None:
    from apps.examinations.queries import result as result_q

    if result_q.get_current_publication(exam.pk):
        return
    payload = compute_results(exam, branch=branch, tenant=tenant)
    publish_results(
        exam,
        branch=branch,
        tenant=tenant,
        confirm_token=payload["confirmToken"],
        note="Demo results published",
        user=admin,
    )


def _seed_branch_core(*, tenant, branch, branch_index: int, code: str):
    """Admins, faculty, academic skeleton (Class 1–5 Section A), students, parents."""
    print(f"\n--- {branch.name} ({code}) ---")
    print("Users:")
    admins = []
    for j in range(1, 4):
        phone = f"+9198765432{branch_index}{j}"
        admins.append(
            _user(
                role=Role.ADMIN,
                tenant=tenant,
                branch=branch,
                first_name="Admin",
                last_name=f"{code} {j}",
                phone=phone,
            )
        )

    faculty_entries = []
    for k, (subj_name, subj_code) in enumerate(SUBJECT_SPECS, start=1):
        login_id = f"FAC-{code}-{k:02d}"
        fac = _user(
            role=Role.FACULTY,
            tenant=tenant,
            branch=branch,
            first_name=subj_name.split()[0],
            last_name=f"Teacher {code}",
            login_id=login_id,
        )
        FacultyProfile.objects.get_or_create(
            user=fac,
            defaults=dict(
                designation="Teacher",
                employment_type="full_time",
                specialization=subj_name,
            ),
        )
        Employee.objects.get_or_create(
            user=fac,
            defaults=dict(
                branch=branch,
                employee_code=login_id,
                employment_type="full_time",
                designation="Teacher",
                joined_at=datetime.date(2024, 6, 1),
                base_components=PAYROLL_COMPONENTS,
            ),
        )
        faculty_entries.append((fac, subj_name, subj_code))

    print("\nAcademic structure:")
    year, _ = AcademicYear.objects.get_or_create(
        branch=branch,
        name="2025-2026",
        defaults=dict(
            start_date=datetime.date(2025, 6, 1),
            end_date=datetime.date(2026, 4, 30),
            is_current=True,
        ),
    )
    period, _ = AcademicPeriod.objects.get_or_create(
        academic_year=year,
        sequence=1,
        defaults=dict(
            period_type=PeriodType.TERM,
            name="Term 1",
            start_date=year.start_date,
            end_date=year.end_date,
        ),
    )
    dept, _ = Department.objects.get_or_create(
        branch=branch,
        code="PRI",
        defaults=dict(name="Primary School"),
    )

    batches: dict[int, Batch] = {}
    batch_subjects: dict[tuple[int, str], BatchSubject] = {}
    subjects_by_grade: dict[int, dict[str, Subject]] = {}

    for grade in range(1, 6):
        course, _ = Course.objects.get_or_create(
            department=dept,
            code=f"C{grade}",
            defaults=dict(name=f"Class {grade}"),
        )
        batch, _ = Batch.objects.get_or_create(
            course=course,
            academic_year=year,
            name="A",
            defaults=dict(capacity=40),
        )
        batch.class_teacher = faculty_entries[grade - 1][0]
        batch.save(update_fields=["class_teacher"])
        batches[grade] = batch
        subjects_by_grade[grade] = {}
        print(f"  - Class {grade} - A (class teacher: {faculty_entries[grade - 1][0].custom_login_id})")

        for fac, subj_name, subj_code in faculty_entries:
            subj, _ = Subject.objects.get_or_create(
                course=course,
                code=f"{subj_code}{grade}",
                defaults=dict(name=subj_name),
            )
            subjects_by_grade[grade][subj_name] = subj
            bs, _ = BatchSubject.objects.get_or_create(
                batch=batch,
                subject=subj,
                academic_period=period,
            )
            batch_subjects[(grade, subj_name)] = bs
            BatchFaculty.objects.get_or_create(
                batch_subject=bs,
                faculty=fac,
                defaults=dict(role="primary", assigned_at=datetime.date(2025, 6, 1)),
            )

    print("\nParents:")
    parents = []
    for p in range(1, 11):
        phone = f"+9198765433{branch_index}{p}"
        parent = _user(
            role=Role.PARENT,
            tenant=tenant,
            branch=branch,
            first_name="Parent",
            last_name=f"{code} {p:02d}",
            phone=phone,
        )
        parents.append(parent)

    print("\nStudents + enrollments:")
    enrollments = []
    for grade in range(1, 6):
        batch = batches[grade]
        for nn in range(1, 6):
            login_id = f"STU-{code}-{grade}A-{nn:02d}"
            first = f"Student{nn}"
            last = f"Class{grade}{code}"
            student = _user(
                role=Role.STUDENT,
                tenant=tenant,
                branch=branch,
                first_name=first,
                last_name=last,
                login_id=login_id,
            )
            parent = parents[(grade * nn - 1) % len(parents)]
            enr = _enroll_student(
                user=student,
                branch=branch,
                batch=batch,
                year=year,
                dob=datetime.date(2015 - grade, 3, nn),
                gender="female" if nn % 2 == 0 else "male",
            )
            _link_parent(student=student, guardian=parent)
            enrollments.append(enr)
            print(f"  - {first} {last} ({login_id}) → Class {grade} - A")

    return dict(
        admins=admins,
        faculty_entries=faculty_entries,
        year=year,
        period=period,
        dept=dept,
        batches=batches,
        batch_subjects=batch_subjects,
        subjects_by_grade=subjects_by_grade,
        parents=parents,
        enrollments=enrollments,
    )


def _seed_branch_light(*, tenant, branch, ctx) -> None:
    """Light attendance + fees for non-primary branches."""
    admin = ctx["admins"][0]
    faculty = ctx["faculty_entries"][0][0]
    class5_batch = ctx["batches"][5]
    class5_enrollments = [e for e in ctx["enrollments"] if e.batch_id == class5_batch.pk]

    print("\nFees (light):")
    for enr in class5_enrollments[:2]:
        amount = 3_500_000
        invoice, created_inv = FeeInvoice.objects.get_or_create(
            student=enr,
            branch=branch,
            defaults=dict(
                due_date=datetime.date(2025, 7, 31),
                total_paise=amount,
                paid_paise=amount // 2,
                status="partial",
            ),
        )
        if created_inv:
            FeeInvoiceLine.objects.create(
                invoice=invoice,
                label="Tuition Fee (Term 1)",
                amount_paise=amount,
            )
    print(f"  - {min(2, len(class5_enrollments))} fee invoices")

    print("\nAttendance (light):")
    d = datetime.date.today()
    sessions = 0
    while sessions < 5:
        if d.isoweekday() <= 5:
            sess, _ = AttendanceSession.objects.get_or_create(
                branch=branch,
                batch=class5_batch,
                mode="day",
                date=d,
                defaults=dict(faculty=faculty, status="completed"),
            )
            for enr in class5_enrollments:
                AttendanceRecord.objects.get_or_create(
                    session=sess,
                    student=enr,
                    defaults=dict(
                        status="present",
                        marked_at=timezone.now(),
                        marked_by=faculty,
                        idempotency_key=f"{sess.pk}:{enr.pk}",
                    ),
                )
            sessions += 1
        d -= datetime.timedelta(days=1)
    print(f"  - {sessions} attendance sessions (Class 5-A)")


def _seed_main_campus_rich(*, tenant, branch, ctx) -> None:
    """Rich demo content — homework, exams, grievances, payroll, etc."""
    admin = ctx["admins"][0]
    faculty = ctx["faculty_entries"][0][0]
    faculty2 = ctx["faculty_entries"][1][0]
    year = ctx["year"]
    period = ctx["period"]
    class5_batch = ctx["batches"][5]
    batch_subjects = ctx["batch_subjects"]
    subjects = ctx["subjects_by_grade"][5]
    enrollments = ctx["enrollments"]
    class5_enrollments = [e for e in enrollments if e.batch_id == class5_batch.pk]

    print("\nHR:")
    employee = Employee.objects.get(user=faculty)
    fy = financial_year_for(datetime.date.today())
    for leave_type, days in (("casual", 12), ("sick", 10), ("earned", 15)):
        LeaveBalance.objects.get_or_create(
            employee=employee,
            leave_type=leave_type,
            year=fy,
            defaults=dict(balance_days=days),
        )
    print(f"  - Leave balances for {fy}")

    working = set(branch.working_days or [1, 2, 3, 4, 5, 6])
    today_d = datetime.date.today()
    for fac in (faculty, faculty2):
        present_days = 0
        for day in range(1, today_d.day + 1):
            d = datetime.date(today_d.year, today_d.month, day)
            if (d.isoweekday() % 7) in working:
                StaffAttendance.objects.get_or_create(
                    user=fac,
                    date=d,
                    defaults=dict(
                        branch=branch,
                        status="present",
                        marked_at=timezone.now(),
                        created_by=admin,
                        updated_by=admin,
                    ),
                )
                present_days += 1
        print(f"  - {fac.custom_login_id}: present on {present_days} day(s) this month")

    last_month = (today_d.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
    payroll_run, created_run = PayrollRun.objects.get_or_create(
        branch=branch,
        period_month=last_month,
        defaults=dict(
            status=PayrollRunStatus.SUCCEEDED,
            executed_at=timezone.now(),
            executed_by=admin,
        ),
    )
    if created_run or not payroll_run.payslips.exists():
        Payslip.objects.get_or_create(
            payroll_run=payroll_run,
            employee=employee,
            defaults=dict(
                components=PAYROLL_COMPONENTS,
                gross_paise=4_200_000,
                deductions_paise=180_000,
                net_paise=PAYROLL_NET,
                worked_days=22,
                payable_days=22,
                pro_rated=False,
            ),
        )
        payroll_run.locked_at = timezone.now()
        payroll_run.status = PayrollRunStatus.LOCKED
        payroll_run.totals = {"grossPaise": 4_200_000, "netPaise": PAYROLL_NET, "employeeCount": 1}
        payroll_run.save()
    print("  - 1 processed payroll run with payslip")

    print("\nSyllabus:")
    for i, title in enumerate(
        ["Numbers & Place Value", "Addition & Subtraction", "Multiplication", "Fractions"],
        start=1,
    ):
        SyllabusUnit.objects.get_or_create(
            branch=branch,
            subject=subjects["Mathematics"],
            title=title,
            defaults=dict(order=i),
        )
    math_units = list(
        SyllabusUnit.objects.filter(
            branch=branch,
            subject=subjects["Mathematics"],
            is_active=True,
        ).order_by("order")[:2]
    )
    for unit in math_units:
        SyllabusUnitProgress.objects.get_or_create(
            branch=branch,
            batch=class5_batch,
            unit=unit,
            defaults=dict(completed_at=timezone.now(), completed_by=faculty),
        )
    print(f"  - Syllabus units + {len(math_units)} completed (Class 5-A Maths)")

    print("\nHomework:")
    hw_plan = [
        ("Fractions worksheet", "Complete exercises 1-10 on page 45."),
        ("English essay: My favourite season", "Write 150 words; submit tomorrow."),
        ("Science reading", "Read chapter 6 and note 5 key points."),
    ]
    for i, (title, details) in enumerate(hw_plan):
        Homework.objects.get_or_create(
            branch=branch,
            batch=class5_batch,
            title=title,
            defaults=dict(
                date=_days_ago(i % 5),
                details=details,
                status="published",
                published_at=timezone.now(),
                created_by=faculty,
                updated_by=faculty,
            ),
        )
    print(f"  - {len(hw_plan)} homework items (Class 5-A)")

    print("\nStudy materials:")
    folder, _ = StudyMaterialFolder.objects.get_or_create(
        branch=branch,
        batch=class5_batch,
        name="Unit 1",
        defaults=dict(sort_order=1),
    )
    for file_name in ("chapter-notes.pdf", "practice-questions.pdf"):
        StudyMaterial.objects.get_or_create(
            branch=branch,
            batch=class5_batch,
            file_name=file_name,
            defaults=dict(
                folder=folder,
                s3_key=f"materials/demo/{class5_batch.pk}/{file_name}",
                url=f"https://example.com/materials/{file_name}",
                uploaded_by=admin,
            ),
        )
    print("  - Folders + materials for Class 5-A")

    print("\nAnnouncements:")
    for title, body in (
        ("Welcome to the new academic year!", "School reopens on June 1. Please check your timetable."),
        ("PTM scheduled next month", "Parent-teacher meetings for primary classes are on the calendar."),
        ("Sports day practice", "Students registered for sports events should attend evening practice."),
        ("Fee reminder", "Term 1 fee payment deadline is approaching. Clear dues to avoid penalties."),
    ):
        Announcement.objects.get_or_create(
            branch=branch,
            title=title,
            defaults=dict(
                body=body,
                target_type=AnnouncementTargetType.ALL,
                target_label="Everyone",
                channels=["in_app"],
                created_by=faculty,
            ),
        )
    print("  - 4 announcements")

    print("\nFees:")
    for enr in class5_enrollments[:3]:
        amount = 5_000_000
        invoice, created_inv = FeeInvoice.objects.get_or_create(
            student=enr,
            branch=branch,
            defaults=dict(
                due_date=datetime.date(2025, 7, 31),
                total_paise=amount,
                paid_paise=0,
                status="due",
            ),
        )
        if created_inv:
            FeeInvoiceLine.objects.create(
                invoice=invoice,
                label="Tuition Fee (Term 1)",
                amount_paise=amount,
            )
    print(f"  - {min(3, len(class5_enrollments))} fee invoices")

    print("\nTimetable + attendance:")
    slot1, _ = PeriodSlot.objects.get_or_create(
        branch=branch,
        sequence=1,
        defaults=dict(name="Period 1", start_time=datetime.time(9, 0), end_time=datetime.time(9, 45)),
    )
    slot2, _ = PeriodSlot.objects.get_or_create(
        branch=branch,
        sequence=2,
        defaults=dict(name="Period 2", start_time=datetime.time(9, 50), end_time=datetime.time(10, 35)),
    )
    timetable, _ = Timetable.objects.get_or_create(
        batch=class5_batch,
        academic_period=period,
        defaults=dict(is_published=True),
    )
    for day in range(1, 6):
        TimetableEntry.objects.get_or_create(
            timetable=timetable,
            batch_subject=batch_subjects[(5, "Mathematics")],
            period_slot=slot1,
            day_of_week=day,
            defaults=dict(faculty=faculty, status="active"),
        )
        TimetableEntry.objects.get_or_create(
            timetable=timetable,
            batch_subject=batch_subjects[(5, "English")],
            period_slot=slot2,
            day_of_week=day,
            defaults=dict(faculty=faculty, status="active"),
        )
    print("  - Maths + English timetabled Mon-Fri (Class 5-A)")

    d = datetime.date.today()
    total_sessions = 0
    while total_sessions < 14:
        if d.isoweekday() <= 5:
            sess, _ = AttendanceSession.objects.get_or_create(
                branch=branch,
                batch=class5_batch,
                mode="day",
                date=d,
                defaults=dict(faculty=faculty, status="completed"),
            )
            for enr in class5_enrollments:
                login = enr.student_profile.user.custom_login_id or ""
                status = "absent" if login.endswith("-05") and total_sessions % 6 == 5 else "present"
                AttendanceRecord.objects.get_or_create(
                    session=sess,
                    student=enr,
                    defaults=dict(
                        status=status,
                        marked_at=timezone.now(),
                        marked_by=faculty,
                        idempotency_key=f"{sess.pk}:{enr.pk}",
                    ),
                )
            total_sessions += 1
        d -= datetime.timedelta(days=1)
    print(f"  - {total_sessions} attendance sessions (Class 5-A)")

    print("\nExams + published results:")
    room, _ = Room.objects.get_or_create(
        branch=branch,
        name="Room 101",
        defaults=dict(capacity=40),
    )
    exam_plan = [
        ("Unit Test 1", datetime.date(2025, 8, 10), 0),
        ("Mid-Term", datetime.date(2025, 11, 5), 6),
    ]
    base_marks = {"English": 70, "Mathematics": 72, "Science": 66}
    created_exams = []
    for exam_name, exam_date, bump in exam_plan:
        exam, _ = Exam.objects.get_or_create(
            branch=branch,
            academic_period=period,
            name=exam_name,
            defaults=dict(
                exam_type="internal",
                exam_fee_paise=0,
                is_published=True,
                marks_deadline=timezone.make_aware(
                    datetime.datetime.combine(exam_date, datetime.time(17, 0))
                ),
            ),
        )
        if not exam.is_published:
            exam.is_published = True
            exam.save(update_fields=["is_published"])
        for subj_name in ("English", "Mathematics", "Science"):
            subj = subjects[subj_name]
            ExamScheduleSlot.objects.get_or_create(
                exam=exam,
                subject=subj,
                batch=class5_batch,
                defaults=dict(
                    room=room,
                    max_marks=100,
                    start_at=timezone.make_aware(
                        datetime.datetime.combine(exam_date, datetime.time(9, 0))
                    ),
                    end_at=timezone.make_aware(
                        datetime.datetime.combine(exam_date, datetime.time(11, 0))
                    ),
                ),
            )
            for enr in class5_enrollments:
                login = enr.student_profile.user.custom_login_id or ""
                extra = 4 if login.endswith("-02") else (-2 if login.endswith("-03") else 0)
                MarksEntry.objects.get_or_create(
                    exam=exam,
                    subject=subj,
                    student=enr,
                    defaults=dict(
                        marks=min(base_marks[subj_name] + bump + extra, 100),
                        marks_status=MarksStatus.LOCKED,
                        is_absent=False,
                    ),
                )
        created_exams.append(exam)
        print(f"  - {exam_name} (marks for {len(class5_enrollments)} students)")

    for exam in created_exams:
        try:
            _publish_exam_results(exam, branch=branch, tenant=tenant, admin=admin)
            print(f"  - Published results: {exam.name}")
        except Exception as exc:
            print(f"  - Skipped publish for {exam.name}: {exc}")

    print("\nGrievances:")
    sample_student = class5_enrollments[2].student_profile.user if len(class5_enrollments) > 2 else None
    if sample_student:
        Grievance.objects.get_or_create(
            branch=branch,
            student=sample_student,
            subject="Bus route timing",
            defaults=dict(
                raised_by=ctx["parents"][0],
                raised_by_role=GrievanceRaiserRole.PARENT,
                category="Transport",
                description="The morning bus has been arriving 20 minutes late.",
                status=GrievanceStatus.OPEN,
            ),
        )
    sample_student2 = class5_enrollments[3].student_profile.user if len(class5_enrollments) > 3 else None
    if sample_student2:
        Grievance.objects.get_or_create(
            branch=branch,
            student=sample_student2,
            subject="Grade discrepancy in unit test",
            defaults=dict(
                raised_by=sample_student2,
                raised_by_role=GrievanceRaiserRole.STUDENT,
                category="Academic",
                description="My mathematics unit test marks do not match the answer key.",
                status=GrievanceStatus.IN_REVIEW,
                assigned_to=admin,
                assigned_at=timezone.now(),
            ),
        )
    print("  - 2 grievances (open + in review)")


def reset_data():
    """Remove ALL existing rows from every table (keeps schema). Destructive."""
    print("Wiping all existing data (manage.py flush)...")
    call_command("flush", "--no-input")
    print("  - database emptied.\n")


def seed():
    print(f"\nSeeding {SCHOOL_NAME} ({SUBDOMAIN}.eduos.app)\n")

    tenant, _ = Tenant.objects.get_or_create(
        subdomain=SUBDOMAIN,
        defaults=dict(
            name=SCHOOL_NAME,
            institution_type="school",
            status="active",
            city=CITY,
            state=STATE,
            parent_access_enabled=True,
        ),
    )
    TenantSettings.objects.get_or_create(
        tenant=tenant,
        defaults=dict(
            student_id_label="Roll Number",
            faculty_id_label="Employee ID",
            attendance_mode="day",
        ),
    )
    PlanSubscription.objects.get_or_create(
        tenant=tenant,
        defaults=dict(plan="starter", billing_status="trial", **_PLAN),
    )
    for resource, hard in (
        ("students", _PLAN["student_limit"]),
        ("sms_count", _PLAN["sms_quota_per_month"]),
        ("ai_tokens", _PLAN["ai_token_quota_per_month"]),
    ):
        TenantQuota.objects.get_or_create(
            tenant=tenant,
            resource=resource,
            period_start=datetime.date.today().replace(day=1),
            defaults=dict(period="month", usage=0, soft_cap=int(hard * 0.9), hard_cap=hard),
        )

    print("Users:")
    _user(
        role=Role.SUPER_ADMIN,
        tenant=tenant,
        branch=None,
        first_name="Ravi",
        last_name="SuperAdmin",
        phone=SUPER_ADMIN_PHONE,
    )

    branch_contexts = []
    for idx, spec in enumerate(BRANCH_SPECS):
        branch, _ = Branch.objects.get_or_create(
            tenant=tenant,
            code=spec["code"],
            defaults=dict(
                name=spec["name"],
                is_primary=spec["is_primary"],
                city=CITY,
                state=STATE,
            ),
        )
        if branch.name != spec["name"]:
            branch.name = spec["name"]
            branch.is_primary = spec["is_primary"]
            branch.save(update_fields=["name", "is_primary"])
        ctx = _seed_branch_core(tenant=tenant, branch=branch, branch_index=idx, code=spec["code"])
        branch_contexts.append((branch, spec, ctx))
        if spec["rich"]:
            _seed_main_campus_rich(tenant=tenant, branch=branch, ctx=ctx)
        else:
            _seed_branch_light(tenant=tenant, branch=branch, ctx=ctx)

    print("\n" + "=" * 52)
    print(f"Done. Login at {SUBDOMAIN}.<your-domain>")
    print(f"All passwords: {PASSWORD}")
    print(f"  Super Admin : {SUPER_ADMIN_PHONE}")
    for branch, spec, ctx in branch_contexts:
        print(f"\n  [{spec['name']} — {spec['code']}]")
        print("    Admins  :", ", ".join(a.phone for a in ctx["admins"]))
        print("    Faculty :", ", ".join(f[0].custom_login_id for f in ctx["faculty_entries"]))
        print(
            "    Students:",
            f"STU-{spec['code']}-1A-01 … STU-{spec['code']}-5A-05 (25 total)",
        )
        print("    Parents :", ", ".join(p.phone for p in ctx["parents"][:3]), "…")
    print("=" * 52)


if __name__ == "__main__":
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
