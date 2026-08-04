"""
Seed CMR Lalgadi (greenfield school tenant) with 3 branches:
each branch has 3 admins, 5 faculty (subjects + class teachers Class 1–5 A),
and 25 students (5 per class). Main Campus keeps rich demo content.
Also seeds one platform_owner (SaaS operator, no tenant) for the platform app.

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
from apps.admissions.enums import (  # noqa: E402
    ApplicationStatus,
    DocVerificationStatus,
    EnquirySource,
    EnquiryStatus,
)
from apps.admissions.models.application import Application, ApplicationDocument, Enquiry, Waitlist  # noqa: E402
from apps.admissions.models.enrollment import StudentEnrollment  # noqa: E402
from apps.admissions.queries import application as app_q  # noqa: E402
from apps.attendance.enums import LeaveApplicantRole, LeaveStatus  # noqa: E402
from apps.attendance.models.leave import LeaveRequest  # noqa: E402
from apps.attendance.models.record import AttendanceRecord  # noqa: E402
from apps.attendance.models.session import AttendanceSession  # noqa: E402
from apps.communications.models.announcement import Announcement, AnnouncementTargetType  # noqa: E402
from apps.coursework.models import Homework  # noqa: E402
from apps.examinations.enums import MarksStatus  # noqa: E402
from apps.examinations.interactors.registration import bulk_register_exam  # noqa: E402
from apps.examinations.interactors.result import compute_results, publish_results  # noqa: E402
from apps.examinations.models import Exam, ExamScheduleSlot, MarksEntry  # noqa: E402
from apps.fees.interactors import generate_invoices_for_batch  # noqa: E402
from apps.fees.interactors.payment import RecordOfflinePaymentInteractor  # noqa: E402
from apps.fees.enums import PaymentMethod  # noqa: E402
from apps.fees.helpers.paise import financial_year_for  # noqa: E402
from apps.fees.models import FeeStructure  # noqa: E402
from apps.grievances.models import Grievance, GrievanceRaiserRole, GrievanceStatus  # noqa: E402
from apps.hr.enums import PayrollRunStatus  # noqa: E402
from apps.hr.models import Employee, LeaveBalance, Payslip, PayrollRun, StaffAttendance  # noqa: E402
from apps.organizations.models import (  # noqa: E402
    Branch, PlanSubscription, Tenant, TenantQuota, TenantSettings,
)
from apps.organizations.billing.license_allocator import (  # noqa: E402
    on_student_enrolled,
    record_payment,
)
from apps.organizations.billing.platform_pricing import unit_price_for_tenant  # noqa: E402
from apps.organizations.models.licensing import LicensePayment, StudentLicense  # noqa: E402

PASSWORD = "Password123!"
SUBDOMAIN = "greenfield"
SCHOOL_NAME = "CMR Lalgadi"
CITY, STATE = "Hyderabad", "Telangana"

SUPER_ADMIN_PHONE = "+919876543200"
ADMIN_PHONE = "+919876543210"
PARENT_PHONE = "+919876543220"
PARENT2_PHONE = "+919876543221"

# Platform app (SaaS operator) — no tenant; matches apps/platform login hint.
PLATFORM_OWNER_PHONE = "+919000000001"
PLATFORM_OWNER_PASSWORD = "Platform@123"

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


def _admin_email(*, branch_code: str | None, index: int | None = None) -> str:
    """Dev email for MFA login (admin/super_admin require email OTP, not password)."""
    if branch_code is None:
        return f"superadmin@{SUBDOMAIN}.test"
    suffix = f"{branch_code.lower()}-{index}" if index is not None else branch_code.lower()
    return f"admin-{suffix}@{SUBDOMAIN}.test"


def _user(
    *,
    role,
    tenant,
    branch,
    first_name,
    last_name,
    phone=None,
    login_id=None,
    email=None,
) -> User:
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
            email=email or None,
            must_change_password=False,
            is_active=True,
        ),
    )
    if email and user.email != email:
        user.email = email
        user.save(update_fields=["email"])
    _set_password(user)
    label = login_id or phone
    if email:
        label = f"{label} ({email})"
    print(f"  - {role:<13} {label:<16} [{'created' if created else 'exists'}]")
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
    # Billing roster is driven by StudentLicense rows created at enrollment.
    on_student_enrolled(user)
    return enrollment


def _seed_licensing(*, tenant, branch_contexts, admin) -> None:
    """Ensure every seeded student has a license row, then buy seats with a few unpaid left."""
    print("\nLicensing:")
    for _branch, _spec, ctx in branch_contexts:
        for enr in ctx["enrollments"]:
            on_student_enrolled(enr.student_profile.user, user=admin)

    # Per branch: license 20 of 25 so Billing shows both Licensed and Unpaid.
    price = unit_price_for_tenant(tenant.pk)
    licensed_per_branch = 20
    for branch, spec, _ctx in branch_contexts:
        key = f"seed-cmr-licenses-{spec['code']}-v1"
        if LicensePayment.objects.filter(idempotency_key=key).exists():
            print(f"  - {spec['name']}: license payment already recorded")
            continue
        unlicensed = StudentLicense.objects.filter(
            tenant=tenant,
            branch=branch,
            license_status="unlicensed",
            student_user__is_active=True,
        ).count()
        grant = min(licensed_per_branch, unlicensed)
        if grant <= 0:
            print(f"  - {spec['name']}: no unlicensed seats to convert")
            continue
        record_payment(
            tenant,
            licenses_granted=grant,
            amount_inr=grant * price,
            payment_mode="offline",
            reference_number=f"SEED-{spec['code']}-LIC",
            notes="[seed-cmr] Demo license purchase",
            idempotency_key=key,
            branch_id=branch.pk,
            user=admin,
        )
        print(f"  - {spec['name']}: purchased {grant} licenses (₹{grant * price})")

    total = StudentLicense.objects.filter(tenant=tenant, student_user__is_active=True).count()
    unpaid = StudentLicense.objects.filter(
        tenant=tenant, license_status="unlicensed", student_user__is_active=True
    ).count()
    print(f"  - Roster: {total} students, {unpaid} unpaid")


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
                email=_admin_email(branch_code=code, index=j),
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


def _seed_branch_fees(*, branch, ctx, multi_installment: bool = False) -> None:
    """Fee structures + generated invoices with installments (replaces bare FeeInvoice rows)."""
    admin = ctx["admins"][0]
    year = ctx["year"]
    class5_batch = ctx["batches"][5]
    class5_enrollments = [e for e in ctx["enrollments"] if e.batch_id == class5_batch.pk]
    if not class5_enrollments:
        return

    if multi_installment:
        name = "Class 5-A — 2 terms"
        components = [
            {"kind": "tuition", "label": "Tuition Term 1", "amount_paise": 3_000_000, "due_date": "2025-07-10", "installment_no": 1},
            {"kind": "tuition", "label": "Tuition Term 2", "amount_paise": 2_000_000, "due_date": "2025-10-10", "installment_no": 2},
            {"kind": "transport", "label": "Transport", "amount_paise": 1_000_000, "due_date": "2025-09-10", "installment_no": 2},
        ]
    else:
        name = "Class 5-A — Term 1"
        components = [
            {"kind": "tuition", "label": "Tuition Term 1", "amount_paise": 3_500_000, "due_date": "2025-07-31", "installment_no": 1},
        ]

    fs, created = FeeStructure.objects.get_or_create(
        branch=branch,
        academic_year=year,
        batch=class5_batch,
        name=name,
        defaults=dict(components=components, is_active=True, created_by=admin, updated_by=admin),
    )
    if not created:
        fs.components = components
        fs.save(update_fields=["components", "updated_at"])

    invoices = generate_invoices_for_batch(
        branch=branch,
        batch_id=class5_batch.pk,
        academic_year=year,
        fee_structure=fs,
        user=admin,
    )

    if multi_installment and invoices:
        inv = invoices[0]
        first_inst = inv.installments.order_by("sequence").first()
        if first_inst and first_inst.amount_paise > 0:
            partial = first_inst.amount_paise // 2
            RecordOfflinePaymentInteractor(
                invoice_id=inv.id,
                amount_paise=partial,
                method=PaymentMethod.CASH,
                payer_user=class5_enrollments[0].user,
                user=admin,
            ).execute()

    print(f"  - fee structure + invoices ({name}); generated {len(invoices)} new")


def _seed_exam_fees_demo(*, tenant, branch, ctx) -> None:
    """One paid exam with fee invoices for Class 5-A (student portal exam tab)."""
    admin = ctx["admins"][0]
    period = ctx["period"]
    class5_batch = ctx["batches"][5]
    exam, _ = Exam.objects.get_or_create(
        branch=branch,
        academic_period=period,
        name="Mid-Term Exam Fee Demo",
        defaults=dict(
            exam_type="internal",
            exam_fee_paise=50_000,
            is_published=True,
            marks_deadline=timezone.make_aware(
                datetime.datetime.combine(datetime.date(2025, 9, 15), datetime.time(17, 0))
            ),
        ),
    )
    if exam.exam_fee_paise == 0:
        exam.exam_fee_paise = 50_000
        exam.save(update_fields=["exam_fee_paise"])
    bulk_register_exam(
        exam,
        branch=branch,
        batch_id=class5_batch.pk,
        tenant=tenant,
        user=admin,
    )
    print("  - exam fee registrations for Class 5-A")


def _seed_branch_light(*, tenant, branch, ctx) -> None:
    """Light attendance + fees for non-primary branches."""
    admin = ctx["admins"][0]
    faculty = ctx["faculty_entries"][0][0]
    class5_batch = ctx["batches"][5]
    class5_enrollments = [e for e in ctx["enrollments"] if e.batch_id == class5_batch.pk]

    print("\nFees (light):")
    _seed_branch_fees(branch=branch, ctx=ctx, multi_installment=False)

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

    _seed_branch_exam_results(
        tenant=tenant,
        branch=branch,
        ctx=ctx,
        exam_plan=[("Unit Test 1", datetime.date(2025, 8, 10), 0)],
        label="light",
    )


def _seed_branch_exam_results(
    *,
    tenant,
    branch,
    ctx,
    exam_plan: list[tuple[str, datetime.date, int]],
    label: str = "",
) -> None:
    """Create exams, marks, and published results for Class 5-A."""
    admin = ctx["admins"][0]
    period = ctx["period"]
    class5_batch = ctx["batches"][5]
    subjects = ctx["subjects_by_grade"][5]
    enrollments = ctx["enrollments"]
    class5_enrollments = [e for e in enrollments if e.batch_id == class5_batch.pk]
    if not class5_enrollments:
        return

    prefix = f"Exams + published results{f' ({label})' if label else ''}:"
    print(f"\n{prefix}")
    room, _ = Room.objects.get_or_create(
        branch=branch,
        name="Room 101",
        defaults=dict(capacity=40),
    )
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


_MC_SYLLABUS_UNITS = {
    "Mathematics": [
        "Numbers & Place Value",
        "Addition & Subtraction",
        "Multiplication",
        "Fractions",
    ],
    "English": [
        "Reading Comprehension",
        "Grammar Basics",
        "Creative Writing",
        "Vocabulary Builder",
    ],
    "Science": [
        "Living & Non-living",
        "Plants Around Us",
        "Human Body",
        "Matter & Materials",
    ],
    "Social Studies": [
        "My Family & Neighbourhood",
        "Maps & Directions",
        "Our Community Helpers",
        "Festivals of India",
    ],
    "Hindi": [
        "वर्णमाला एवं मात्राएँ",
        "सरल वाक्य",
        "कहानी पाठ",
        "कविता एवं श्रुतलेख",
    ],
}


def _seed_mc_admissions_funnel(*, branch, ctx, admin) -> None:
    """Enquiry + application mix so Admissions Funnel / Pipeline / Waitlist look live."""
    print("\nAdmissions funnel:")
    courses = {g: ctx["batches"][g].course for g in range(1, 6)}
    class5_enrollments = [
        e for e in ctx["enrollments"] if e.batch_id == ctx["batches"][5].pk
    ]

    # Open enquiries (show on Funnel "enquiry" stage = new + contacted only).
    open_specs = [
        ("Aarav Mehta", EnquirySource.WALK_IN, EnquiryStatus.NEW, 1),
        ("Diya Kapoor", EnquirySource.SOCIAL, EnquiryStatus.NEW, 2),
        ("Kabir Nair", EnquirySource.ONLINE, EnquiryStatus.NEW, 3),
        ("Ananya Iyer", EnquirySource.REFERRAL, EnquiryStatus.NEW, 1),
        ("Rohan Desai", EnquirySource.WALK_IN, EnquiryStatus.CONTACTED, 4),
        ("Sara Khan", EnquirySource.SOCIAL, EnquiryStatus.CONTACTED, 5),
        ("Vihaan Joshi", EnquirySource.ONLINE, EnquiryStatus.CONTACTED, 2),
        ("Myra Reddy", EnquirySource.REFERRAL, EnquiryStatus.CONTACTED, 3),
        ("Ishaan Bose", EnquirySource.WALK_IN, EnquiryStatus.CONTACTED, 1),
    ]
    lost_specs = [
        ("Neha Pillai", EnquirySource.SOCIAL, EnquiryStatus.LOST, 2),
        ("Arjun Sethi", EnquirySource.ONLINE, EnquiryStatus.LOST, 4),
        ("Tara Menon", EnquirySource.WALK_IN, EnquiryStatus.LOST, 3),
    ]
    # Converted enquiries → one application each across pipeline stages.
    app_specs = [
        ("Priya Sharma", EnquirySource.WALK_IN, ApplicationStatus.DRAFT, 1, False, None),
        ("Advait Rao", EnquirySource.ONLINE, ApplicationStatus.DRAFT, 2, False, None),
        ("Kiara Malhotra", EnquirySource.SOCIAL, ApplicationStatus.SUBMITTED, 3, True, None),
        ("Dev Patel", EnquirySource.REFERRAL, ApplicationStatus.SUBMITTED, 1, False, None),
        ("Saanvi Gupta", EnquirySource.WALK_IN, ApplicationStatus.UNDER_REVIEW, 4, True, None),
        ("Reyansh Kulkarni", EnquirySource.ONLINE, ApplicationStatus.UNDER_REVIEW, 5, False, None),
        ("Aanya Verma", EnquirySource.SOCIAL, ApplicationStatus.ACCEPTED, 2, True, None),
        ("Kabir Singh", EnquirySource.REFERRAL, ApplicationStatus.ACCEPTED, 5, False, None),
        ("Zara Ahmed", EnquirySource.WALK_IN, ApplicationStatus.WAITLISTED, 3, False, 1),
        ("Omkar Das", EnquirySource.ONLINE, ApplicationStatus.WAITLISTED, 4, False, 2),
        ("Lavanya Rao", EnquirySource.SOCIAL, ApplicationStatus.REJECTED, 1, False, None),
        ("Yash Chopra", EnquirySource.REFERRAL, ApplicationStatus.ENROLLED, 5, False, None),
        ("Meera Banerjee", EnquirySource.WALK_IN, ApplicationStatus.ENROLLED, 5, False, None),
    ]

    phone_i = 1

    def _phone() -> str:
        nonlocal phone_i
        p = f"+9198700{phone_i:04d}"
        phone_i += 1
        return p

    def _upsert_enquiry(*, name, source, status, grade, phone) -> Enquiry:
        enquiry, created = Enquiry.objects.get_or_create(
            branch=branch,
            phone=phone,
            defaults=dict(
                source=source,
                applicant_name=name,
                course=courses[grade],
                email=f"{name.split()[0].lower()}.seed@example.com",
                status=status,
                captured_by=admin,
                notes="[seed-cmr] Main Campus demo enquiry",
                created_by=admin,
                updated_by=admin,
            ),
        )
        if not created and (
            enquiry.status != status
            or enquiry.source != source
            or enquiry.applicant_name != name
        ):
            enquiry.status = status
            enquiry.source = source
            enquiry.applicant_name = name
            enquiry.course = courses[grade]
            enquiry.updated_by = admin
            enquiry.save(
                update_fields=[
                    "status",
                    "source",
                    "applicant_name",
                    "course",
                    "updated_by",
                    "updated_at",
                ]
            )
        return enquiry

    for name, source, status, grade in open_specs + lost_specs:
        _upsert_enquiry(name=name, source=source, status=status, grade=grade, phone=_phone())

    enrolled_apps: list[Application] = []
    for name, source, app_status, grade, with_docs, waitlist_rank in app_specs:
        phone = _phone()
        enquiry = _upsert_enquiry(
            name=name,
            source=source,
            status=EnquiryStatus.CONVERTED,
            grade=grade,
            phone=phone,
        )
        application, created = Application.objects.get_or_create(
            enquiry=enquiry,
            defaults=dict(
                branch=branch,
                course=courses[grade],
                status=app_status,
                step={"seed": True},
                created_by=admin,
                updated_by=admin,
                rejection_reason=(
                    "Seats full for preferred section"
                    if app_status == ApplicationStatus.REJECTED
                    else ""
                ),
            ),
        )
        if not created and application.status != app_status:
            application.status = app_status
            application.course = courses[grade]
            application.updated_by = admin
            if app_status == ApplicationStatus.REJECTED and not application.rejection_reason:
                application.rejection_reason = "Seats full for preferred section"
            application.save(
                update_fields=[
                    "status",
                    "course",
                    "updated_by",
                    "updated_at",
                    "rejection_reason",
                ]
            )
        if with_docs:
            for doc_type, ver in (
                ("birth_certificate", DocVerificationStatus.VERIFIED),
                ("address_proof", DocVerificationStatus.PENDING),
            ):
                doc, _ = ApplicationDocument.objects.get_or_create(
                    application=application,
                    doc_type=doc_type,
                    defaults=dict(
                        s3_key=f"admissions/demo/{application.pk}/{doc_type}.pdf",
                        verification_status=ver,
                        verified_by=admin if ver == DocVerificationStatus.VERIFIED else None,
                        created_by=admin,
                        updated_by=admin,
                    ),
                )
                if doc.verification_status != ver:
                    doc.verification_status = ver
                    doc.verified_by = admin if ver == DocVerificationStatus.VERIFIED else None
                    doc.save(update_fields=["verification_status", "verified_by", "updated_at"])
        if waitlist_rank is not None:
            app_q.upsert_waitlist(
                branch=branch,
                application=application,
                course=courses[grade],
                rank=waitlist_rank,
                user=admin,
            )
        if app_status == ApplicationStatus.ENROLLED:
            enrolled_apps.append(application)

    for app, enr in zip(enrolled_apps, class5_enrollments[: len(enrolled_apps)]):
        if enr.application_id != app.pk:
            enr.application = app
            enr.save(update_fields=["application", "updated_at"])

    n_enq = Enquiry.objects.filter(branch=branch, notes__contains="[seed-cmr]").count()
    n_app = Application.objects.filter(branch=branch, step__seed=True).count()
    n_wl = Waitlist.objects.filter(branch=branch, is_active=True).count()
    print(f"  - {n_enq} seeded enquiries, {n_app} applications, {n_wl} waitlist entries")


def _seed_mc_syllabus(*, branch, ctx) -> None:
    """Syllabus units for Class 1-A and 5-A (all subjects) with partial completion."""
    print("\nSyllabus:")
    faculty_by_subject = {name: fac for fac, name, _code in ctx["faculty_entries"]}
    completed = 0
    total_units = 0
    for grade in (1, 5):
        batch = ctx["batches"][grade]
        subjects = ctx["subjects_by_grade"][grade]
        class_teacher = batch.class_teacher or ctx["faculty_entries"][grade - 1][0]
        for subj_name, titles in _MC_SYLLABUS_UNITS.items():
            subject = subjects[subj_name]
            completed_by = faculty_by_subject.get(subj_name) or class_teacher
            # Leave ~40–60% complete: finish first 2 of 4 for most; 1 of 4 for Hindi on C1.
            n_complete = 1 if (grade == 1 and subj_name == "Hindi") else 2
            for i, title in enumerate(titles, start=1):
                unit, _ = SyllabusUnit.objects.get_or_create(
                    branch=branch,
                    subject=subject,
                    title=title,
                    defaults=dict(order=i),
                )
                total_units += 1
                if i <= n_complete:
                    SyllabusUnitProgress.objects.get_or_create(
                        branch=branch,
                        batch=batch,
                        unit=unit,
                        defaults=dict(
                            completed_at=timezone.now(),
                            completed_by=completed_by,
                        ),
                    )
                    completed += 1
    print(
        f"  - Units for Class 1-A & 5-A (all subjects); "
        f"{completed}/{total_units} marked complete (partial)"
    )


def _seed_mc_day_attendance(*, branch, batch, enrollments, faculty, sessions: int = 12) -> int:
    """Seed weekday day-mode attendance sessions with a few absences."""
    d = datetime.date.today()
    total_sessions = 0
    while total_sessions < sessions:
        if d.isoweekday() <= 5:
            sess, _ = AttendanceSession.objects.get_or_create(
                branch=branch,
                batch=batch,
                mode="day",
                date=d,
                defaults=dict(faculty=faculty, status="completed"),
            )
            for enr in enrollments:
                login = enr.student_profile.user.custom_login_id or ""
                status = (
                    "absent"
                    if login.endswith("-05") and total_sessions % 6 == 5
                    else "absent"
                    if login.endswith("-03") and total_sessions % 7 == 3
                    else "present"
                )
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
    return total_sessions


def _seed_mc_attendance_leaves(*, branch, ctx, admin) -> None:
    """Day attendance for Class 1-A / 3-A / 5-A plus student & staff leave requests."""
    print("\nAttendance + leaves:")
    enrollments = ctx["enrollments"]
    faculty_entries = ctx["faculty_entries"]
    for grade in (1, 3, 5):
        batch = ctx["batches"][grade]
        fac = batch.class_teacher or faculty_entries[grade - 1][0]
        batch_enrs = [e for e in enrollments if e.batch_id == batch.pk]
        n = _seed_mc_day_attendance(
            branch=branch,
            batch=batch,
            enrollments=batch_enrs,
            faculty=fac,
            sessions=12 if grade != 5 else 14,
        )
        print(f"  - {n} attendance sessions (Class {grade}-A, {len(batch_enrs)} students)")

    class5_enrs = [e for e in enrollments if e.batch_id == ctx["batches"][5].pk]
    student_leave_specs = [
        (0, _days_ago(10), _days_ago(9), LeaveStatus.APPROVED, "Family function"),
        (1, _days_ago(3), _days_ago(2), LeaveStatus.PENDING, "Medical checkup"),
        (2, _days_ago(1), datetime.date.today(), LeaveStatus.APPROVED, "Fever"),
    ]
    for idx, from_d, to_d, status, reason in student_leave_specs:
        if idx >= len(class5_enrs):
            break
        enr = class5_enrs[idx]
        student_user = enr.student_profile.user
        leave, created = LeaveRequest.objects.get_or_create(
            branch=branch,
            student=enr,
            from_date=from_d,
            to_date=to_d,
            defaults=dict(
                applicant_role=LeaveApplicantRole.STUDENT,
                reason=reason,
                status=status,
                applied_by=student_user,
                created_by=student_user,
                updated_by=admin,
                approver=admin if status == LeaveStatus.APPROVED else None,
                approved_at=timezone.now() if status == LeaveStatus.APPROVED else None,
            ),
        )
        if not created and leave.status != status:
            leave.status = status
            leave.approver = admin if status == LeaveStatus.APPROVED else None
            leave.approved_at = timezone.now() if status == LeaveStatus.APPROVED else None
            leave.save(update_fields=["status", "approver", "approved_at", "updated_at"])

    staff_leave_specs = [
        (0, _days_ago(7), _days_ago(6), LeaveStatus.APPROVED, "Personal work"),
        (1, _days_ago(2), _days_ago(1), LeaveStatus.PENDING, "Medical leave"),
        (
            2,
            datetime.date.today(),
            datetime.date.today() + datetime.timedelta(days=1),
            LeaveStatus.APPROVED,
            "Half-day family event",
        ),
    ]
    for fac_idx, from_d, to_d, status, reason in staff_leave_specs:
        fac = faculty_entries[fac_idx][0]
        leave, created = LeaveRequest.objects.get_or_create(
            branch=branch,
            employee=fac,
            from_date=from_d,
            to_date=to_d,
            defaults=dict(
                applicant_role=LeaveApplicantRole.STAFF,
                reason=reason,
                status=status,
                applied_by=fac,
                created_by=fac,
                updated_by=admin,
                approver=admin if status == LeaveStatus.APPROVED else None,
                approved_at=timezone.now() if status == LeaveStatus.APPROVED else None,
            ),
        )
        if not created and leave.status != status:
            leave.status = status
            leave.approver = admin if status == LeaveStatus.APPROVED else None
            leave.approved_at = timezone.now() if status == LeaveStatus.APPROVED else None
            leave.save(update_fields=["status", "approver", "approved_at", "updated_at"])

    n_student = LeaveRequest.objects.filter(
        branch=branch, applicant_role=LeaveApplicantRole.STUDENT, is_active=True
    ).count()
    n_staff = LeaveRequest.objects.filter(
        branch=branch, applicant_role=LeaveApplicantRole.STAFF, is_active=True
    ).count()
    print(f"  - Leave requests: {n_student} student, {n_staff} staff")


def _seed_mc_homework_and_teachers(*, branch, ctx) -> None:
    """Re-assert class teachers and seed homework across Class 1 / 3 / 5."""
    print("\nClass teachers + homework:")
    for grade in range(1, 6):
        batch = ctx["batches"][grade]
        expected = ctx["faculty_entries"][grade - 1][0]
        if batch.class_teacher_id != expected.pk:
            batch.class_teacher = expected
            batch.save(update_fields=["class_teacher"])
        print(
            f"  - Class {grade}-A class teacher: {expected.custom_login_id} "
            f"({ctx['faculty_entries'][grade - 1][1]})"
        )

    hw_by_grade = {
        1: [
            ("Alphabet tracing sheet", "Trace letters A–M; submit tomorrow."),
            ("Number bonds to 10", "Complete the worksheet in the notebook."),
            ("Hindi swar practice", "Write each vowel five times neatly."),
        ],
        3: [
            ("Multiplication tables 2–5", "Revise and write once each."),
            ("Science: Parts of a plant", "Draw and label root, stem, leaf."),
            ("English paragraph", "Write 8 sentences about your best friend."),
        ],
        5: [
            ("Fractions worksheet", "Complete exercises 1-10 on page 45."),
            ("English essay: My favourite season", "Write 150 words; submit tomorrow."),
            ("Science reading", "Read chapter 6 and note 5 key points."),
            ("Map skills: India states", "Label 10 states on the outline map."),
        ],
    }
    total = 0
    for grade, items in hw_by_grade.items():
        batch = ctx["batches"][grade]
        fac = batch.class_teacher or ctx["faculty_entries"][grade - 1][0]
        for i, (title, details) in enumerate(items):
            Homework.objects.get_or_create(
                branch=branch,
                batch=batch,
                title=title,
                defaults=dict(
                    date=_days_ago((i * 2 + grade) % 10),
                    details=details,
                    status="published",
                    published_at=timezone.now(),
                    created_by=fac,
                    updated_by=fac,
                ),
            )
            total += 1
    print(f"  - {total} homework items (Classes 1-A, 3-A, 5-A)")


def _seed_main_campus_rich(*, tenant, branch, ctx) -> None:
    """Rich demo content — homework, exams, grievances, payroll, etc."""
    admin = ctx["admins"][0]
    faculty = ctx["faculty_entries"][0][0]
    faculty2 = ctx["faculty_entries"][1][0]
    period = ctx["period"]
    class5_batch = ctx["batches"][5]
    batch_subjects = ctx["batch_subjects"]
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

    _seed_mc_admissions_funnel(branch=branch, ctx=ctx, admin=admin)
    _seed_mc_syllabus(branch=branch, ctx=ctx)
    _seed_mc_homework_and_teachers(branch=branch, ctx=ctx)

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
        ("Library book return drive", "Please return overdue library books by Friday."),
        ("Health checkup camp", "Annual health screening for Classes 1–5 next Wednesday."),
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
    print("  - 6 announcements")

    print("\nFees:")
    _seed_branch_fees(branch=branch, ctx=ctx, multi_installment=True)
    _seed_exam_fees_demo(tenant=tenant, branch=branch, ctx=ctx)

    print("\nTimetable:")
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

    _seed_mc_attendance_leaves(branch=branch, ctx=ctx, admin=admin)

    _seed_branch_exam_results(
        tenant=tenant,
        branch=branch,
        ctx=ctx,
        exam_plan=[
            ("Unit Test 1", datetime.date(2025, 8, 10), 0),
            ("Mid-Term", datetime.date(2025, 11, 5), 6),
        ],
    )

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


def _seed_platform_owner() -> User:
    """SaaS platform owner (tenant-less) for the platform admin app."""
    po, created = User.objects.get_or_create(
        role=Role.PLATFORM_OWNER,
        phone=PLATFORM_OWNER_PHONE,
        defaults=dict(
            first_name="Gopal",
            last_name="Platform Owner",
            tenant=None,
            branch=None,
            must_change_password=False,
            is_active=True,
        ),
    )
    if not po.has_usable_password() or not po.check_password(PLATFORM_OWNER_PASSWORD):
        po.set_password(PLATFORM_OWNER_PASSWORD)
        po.save(update_fields=["password"])
    print(
        f"  - platform_owner {PLATFORM_OWNER_PHONE} "
        f"[{'created' if created else 'exists'}]  (pass: {PLATFORM_OWNER_PASSWORD})"
    )
    return po


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
        defaults=dict(plan="standard", billing_status="paid", **_PLAN),
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
        email=_admin_email(branch_code=None),
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

    super_admin = User.objects.filter(
        tenant=tenant, role=Role.SUPER_ADMIN, phone=SUPER_ADMIN_PHONE
    ).first()
    _seed_licensing(
        tenant=tenant,
        branch_contexts=branch_contexts,
        admin=super_admin or branch_contexts[0][2]["admins"][0],
    )

    print("\nPlatform owner (platform app — not institution portal):")
    _seed_platform_owner()

    print("\n" + "=" * 52)
    print(f"Done. Login at {SUBDOMAIN}.<your-domain>")
    print(f"Institution passwords: {PASSWORD}")
    print(f"  Super Admin : {SUPER_ADMIN_PHONE}")
    print(f"\nPlatform app (pnpm dev:platform):")
    print(f"  Platform Owner: {PLATFORM_OWNER_PHONE} / {PLATFORM_OWNER_PASSWORD}")
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
