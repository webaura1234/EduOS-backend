"""
Seed the database with the two reference institutions the frontend mock-data
assumes: Greenfield Academy (school) and Horizon Engineering College (college).

Each tenant is provisioned end-to-end: primary branch, TenantSettings,
PlanSubscription, TenantQuota counters, a super-admin, an admin, a faculty and a
student. A single platform_owner (no tenant) is also created.

Idempotent — safe to run repeatedly. Run with:  python seed_db.py
"""

import datetime
import os

import django
from django.conf import settings as dj_settings
from django.utils import timezone

# Bootstrap Django only when run as a standalone script (not under pytest, where
# Django is already configured).
if not dj_settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()

from apps.accounts.models.user import Role, User
from apps.accounts.models.profile import StudentProfile  # noqa: E402
from apps.academics.models import AcademicYear, Batch, Course, Department, Room, Subject  # noqa: E402
from apps.academics.models.calendar import AcademicPeriod, PeriodType  # noqa: E402
from apps.admissions.models.enrollment import StudentEnrollment  # noqa: E402
from apps.attendance.models.record import AttendanceRecord  # noqa: E402
from apps.attendance.models.session import AttendanceSession  # noqa: E402
from apps.examinations.enums import MarksStatus  # noqa: E402
from apps.examinations.models import Exam, ExamScheduleSlot, MarksEntry  # noqa: E402
from apps.organizations.models import (  # noqa: E402
    Branch,
    PlanSubscription,
    Tenant,
    TenantQuota,
    TenantSettings,
)

DEFAULT_PASSWORD = "Password123!"
PLATFORM_OWNER_PHONE = "+919000000001"
PLATFORM_OWNER_PASSWORD = "Platform@123"

# Per-plan subscription limits — uncapped for core ERP.
_UNCAPPED_LIMITS = dict(
    student_limit=0,
    storage_limit_gb=0,
    sms_quota_per_month=0,
    ai_token_quota_per_month=0,
    api_rpm_limit=0,
)


def _ensure_password(user: User) -> None:
    if not user.has_usable_password() or not user.check_password(DEFAULT_PASSWORD):
        user.set_password(DEFAULT_PASSWORD)
        user.save(update_fields=["password"])


def _seed_user(*, role, tenant, branch, first_name, last_name,
               phone=None, custom_login_id=None) -> User:
    lookup = {"role": role, "tenant": tenant}
    if custom_login_id:
        lookup["custom_login_id"] = custom_login_id
    else:
        lookup["phone"] = phone
    user, created = User.objects.get_or_create(
        **lookup,
        defaults=dict(
            first_name=first_name, last_name=last_name, branch=branch,
            phone=phone, custom_login_id=custom_login_id,
            must_change_password=False, is_active=True,
        ),
    )
    _ensure_password(user)
    tag = "created" if created else "exists"
    ident = custom_login_id or phone
    print(f"  - {role:<13} {ident:<16} [{tag}]  (pass: {DEFAULT_PASSWORD})")
    if role == Role.STUDENT:
        StudentProfile.objects.get_or_create(
            user=user,
            defaults=dict(admission_date=datetime.date.today()),
        )
    return user


def _seed_quota(tenant, resource, soft_cap, hard_cap) -> None:
    TenantQuota.objects.get_or_create(
        tenant=tenant, resource=resource,
        period_start=datetime.date.today().replace(day=1),
        defaults=dict(period="month", usage=0, soft_cap=soft_cap, hard_cap=hard_cap),
    )


def seed_tenant(*, subdomain, name, institution_type, plan, city, state,
                student_id_label, faculty_id_label, parent_access_enabled,
                phone_prefix) -> Tenant:
    print(f"\n{name} ({institution_type}) — {subdomain}.eduos.app")

    tenant, _ = Tenant.objects.get_or_create(
        subdomain=subdomain,
        defaults=dict(name=name, institution_type=institution_type, status="active",
                      city=city, state=state, parent_access_enabled=parent_access_enabled),
    )
    branch, _ = Branch.objects.get_or_create(
        tenant=tenant, name="Main Campus",
        defaults=dict(code="MC", is_primary=True, city=city, state=state),
    )
    TenantSettings.objects.get_or_create(
        tenant=tenant,
        defaults=dict(student_id_label=student_id_label, faculty_id_label=faculty_id_label),
    )
    limits = _UNCAPPED_LIMITS
    sub, created = PlanSubscription.objects.get_or_create(
        tenant=tenant,
        defaults=dict(plan=plan, billing_status="trial", **limits),
    )
    if not created and sub.plan != plan:
        sub.plan = plan
        sub.save(update_fields=["plan", "updated_at"])
    if limits["student_limit"] > 0:
        _seed_quota(tenant, "students", soft_cap=int(limits["student_limit"] * 0.9),
                    hard_cap=limits["student_limit"])
    if limits["sms_quota_per_month"] > 0:
        _seed_quota(tenant, "sms_count", soft_cap=int(limits["sms_quota_per_month"] * 0.9),
                    hard_cap=limits["sms_quota_per_month"])
    if limits["ai_token_quota_per_month"] > 0:
        _seed_quota(tenant, "ai_tokens", soft_cap=int(limits["ai_token_quota_per_month"] * 0.9),
                    hard_cap=limits["ai_token_quota_per_month"])

    _seed_user(role=Role.SUPER_ADMIN, tenant=tenant, branch=None,
               first_name=name.split()[0], last_name="SuperAdmin", phone=f"{phone_prefix}00")
    admin = _seed_user(role=Role.ADMIN, tenant=tenant, branch=branch,
               first_name=name.split()[0], last_name="Admin", phone=f"{phone_prefix}10")
    faculty = _seed_user(role=Role.FACULTY, tenant=tenant, branch=branch,
               first_name="Priya", last_name="Patel", custom_login_id="FAC-001")
    student = _seed_user(role=Role.STUDENT, tenant=tenant, branch=branch,
               first_name="Rahul", last_name="Sharma", custom_login_id="STU-001")
    _seed_demo_performance(
        tenant=tenant,
        branch=branch,
        institution_type=institution_type,
        admin=admin,
        faculty=faculty,
        student=student,
    )
    return tenant


# Demo marks / attendance for STU-001 so admin performance chat has real data.
_DEMO_SUBJECTS = {
    "school": (
        ("Mathematics", "MAT", 92),
        ("Science", "SCI", 86),
        ("English", "ENG", 34),
        ("Social Studies", "SST", 58),
    ),
    "college": (
        ("Data Structures", "DS", 91),
        ("Database Systems", "DB", 84),
        ("Engineering Mathematics", "MATH", 88),
        ("Programming", "PROG", 37),
    ),
}


def _seed_demo_performance(*, tenant, branch, institution_type, admin, faculty, student) -> None:
    print("  Demo performance (STU-001):")
    profile, _ = StudentProfile.objects.get_or_create(
        user=student,
        defaults=dict(admission_date=datetime.date(2024, 6, 1)),
    )

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

    if institution_type == "college":
        dept_name, dept_code = "Computer Science", "CSE"
        course_name, course_code, batch_name = "B.Tech CSE", "BTCS", "Year 2 - A"
    else:
        dept_name, dept_code = "Secondary", "SEC"
        course_name, course_code, batch_name = "Class 10", "C10", "A"

    dept, _ = Department.objects.get_or_create(
        branch=branch, code=dept_code, defaults=dict(name=dept_name),
    )
    course, _ = Course.objects.get_or_create(
        department=dept, code=course_code, defaults=dict(name=course_name),
    )
    batch, _ = Batch.objects.get_or_create(
        course=course, academic_year=year, name=batch_name, defaults=dict(capacity=40),
    )

    enrollment, _ = StudentEnrollment.objects.get_or_create(
        student_profile=profile,
        academic_year=year,
        defaults=dict(branch=branch, batch=batch, status="active"),
    )
    if profile.current_batch_id != batch.pk or profile.current_enrollment_id != enrollment.pk:
        profile.current_batch = batch
        profile.current_enrollment = enrollment
        profile.save(update_fields=["current_batch", "current_enrollment"])

    subject_specs = _DEMO_SUBJECTS["college" if institution_type == "college" else "school"]
    subjects = []
    for subj_name, subj_code, _ in subject_specs:
        subj, _ = Subject.objects.get_or_create(
            course=course, code=subj_code, defaults=dict(name=subj_name),
        )
        subjects.append(subj)

    exam, _ = Exam.objects.get_or_create(
        branch=branch,
        academic_period=period,
        name="Mid-Term Examination",
        defaults=dict(
            exam_type="internal",
            exam_fee_paise=0,
            is_published=True,
            marks_deadline=timezone.make_aware(
                datetime.datetime.combine(datetime.date(2025, 10, 15), datetime.time(17, 0)),
            ),
        ),
    )

    marks_created = 0
    room, _ = Room.objects.get_or_create(
        branch=branch, name="Room 101", defaults=dict(capacity=40),
    )
    for subj, (_, _, score) in zip(subjects, subject_specs, strict=True):
        ExamScheduleSlot.objects.get_or_create(
            exam=exam,
            subject=subj,
            batch=batch,
            defaults=dict(
                room=room,
                max_marks=100,
                start_at=timezone.make_aware(
                    datetime.datetime.combine(datetime.date(2025, 10, 10), datetime.time(9, 0)),
                ),
                end_at=timezone.make_aware(
                    datetime.datetime.combine(datetime.date(2025, 10, 10), datetime.time(12, 0)),
                ),
            ),
        )
        _, created = MarksEntry.objects.get_or_create(
            exam=exam,
            subject=subj,
            student=enrollment,
            defaults=dict(marks=score, marks_status=MarksStatus.LOCKED, is_absent=False),
        )
        if created:
            marks_created += 1

    attendance_days = 0
    present_count = 0
    d = datetime.date.today()
    while attendance_days < 20:
        if d.isoweekday() <= 5:
            status = "present" if attendance_days < 17 else "absent"
            sess, _ = AttendanceSession.objects.get_or_create(
                branch=branch,
                batch=batch,
                mode="day",
                date=d,
                defaults=dict(faculty=faculty, status="completed"),
            )
            AttendanceRecord.objects.get_or_create(
                session=sess,
                student=enrollment,
                defaults=dict(
                    status=status,
                    marked_at=timezone.now(),
                    marked_by=faculty,
                    idempotency_key=f"{sess.pk}:{enrollment.pk}",
                ),
            )
            if status == "present":
                present_count += 1
            attendance_days += 1
        d -= datetime.timedelta(days=1)

    avg_marks = round(sum(s for _, _, s in subject_specs) / len(subject_specs), 1)
    att_pct = round(present_count / attendance_days * 100, 1)
    print(
        f"    batch={batch_name}, marks={marks_created} new, "
        f"attendance={att_pct}% ({present_count}/{attendance_days}), avg marks~{avg_marks}%"
    )


def seed():
    print("Seeding database...")

    seed_tenant(
        subdomain="greenfield", name="Greenfield Academy", institution_type="school",
        plan="standard", city="Pune", state="Maharashtra",
        student_id_label="Roll Number", faculty_id_label="Employee ID",
        parent_access_enabled=True, phone_prefix="+9198765432",
    )
    seed_tenant(
        subdomain="horizon", name="Horizon Engineering College", institution_type="college",
        plan="ai", city="Bengaluru", state="Karnataka",
        student_id_label="Admission Number", faculty_id_label="Staff Code",
        parent_access_enabled=False, phone_prefix="+9197654321",
    )

    # Platform owner (SaaS operator) — no tenant. Matches frontend mock login hint.
    po, created = User.objects.get_or_create(
        role=Role.PLATFORM_OWNER, phone=PLATFORM_OWNER_PHONE,
        defaults=dict(first_name="Gopal", last_name="Platform Owner",
                      tenant=None, branch=None, must_change_password=False, is_active=True),
    )
    if not po.has_usable_password() or not po.check_password(PLATFORM_OWNER_PASSWORD):
        po.set_password(PLATFORM_OWNER_PASSWORD)
        po.save(update_fields=["password"])
    print(
        f"\nPlatform Owner {PLATFORM_OWNER_PHONE} "
        f"[{'created' if created else 'exists'}]  (pass: {PLATFORM_OWNER_PASSWORD})"
    )

    print("\nSeeding completed successfully!")


if __name__ == "__main__":
    seed()
