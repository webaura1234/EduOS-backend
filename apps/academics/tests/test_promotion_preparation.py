"""Phase 2 — promotion preparation and validation."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.interactors import promotion as prom_i
from apps.academics.interactors import promotion_preparation as prep_i
from apps.academics.interactors import promotion_validation as val_i
from apps.academics.models import AcademicPeriod, AcademicYear, Batch, Course, Department
from apps.academics.models.promotion import ExecutionReadiness, PreparationStatus, PromotionAction
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.enums import EnrollmentStatus
from apps.admissions.models import StudentEnrollment
from apps.fees.enums import FeeStructureStatus, InvoiceStatus
from apps.fees.models import FeeInvoice, FeeStructure
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _data(resp):
    body = resp.json()
    return body.get("data", body)


@pytest.fixture
def college_scenario():
    tenant = TenantFactory(institution_type="college")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYear.objects.create(
        branch=branch,
        name="2024-25",
        is_current=True,
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2025, 4, 30),
    )
    target = AcademicYear.objects.create(
        branch=branch,
        name="2025-26",
        is_current=False,
        start_date=datetime.date(2025, 6, 1),
        end_date=datetime.date(2026, 4, 30),
    )
    AcademicPeriod.objects.create(
        academic_year=year,
        period_type="term",
        sequence=1,
        name="Term 1",
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2024, 10, 31),
    )
    dept = Department.objects.create(branch=branch, name="CSE", department_type="department")
    c1 = Course.objects.create(department=dept, name="Year 1")
    c2 = Course.objects.create(department=dept, name="Year 2")
    batch1 = Batch.objects.create(course=c1, academic_year=year, name="A", capacity=40)
    batch2_target = Batch.objects.create(course=c2, academic_year=target, name="A", capacity=40)

    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        custom_login_id=None,
        must_change_password=False,
    )
    student = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="STU-PH2",
        must_change_password=False,
    )
    profile = StudentProfile.objects.create(
        user=student, current_batch=batch1, academic_status=AcademicStatus.ACTIVE
    )
    StudentEnrollment.objects.create(
        student_profile=profile,
        batch=batch1,
        academic_year=year,
        branch=branch,
        status=EnrollmentStatus.ACTIVE,
    )
    FeeStructure.objects.create(
        branch=branch,
        batch=batch2_target,
        academic_year=target,
        name="Year 2 Fee Structure",
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 5000000, "installment_no": 1}],
        status=FeeStructureStatus.PUBLISHED,
    )

    return {
        "tenant": tenant,
        "branch": branch,
        "year": year,
        "target": target,
        "batch1": batch1,
        "batch2_target": batch2_target,
        "c1": c1,
        "c2": c2,
        "student": student,
        "profile": profile,
        "admin": admin,
    }


@pytest.fixture
def approved_session(college_scenario):
    sc = college_scenario
    started = prom_i.start_promotion(
        branch=sc["branch"],
        tenant=sc["tenant"],
        source_year_id=sc["year"].pk,
        target_year_id=sc["target"].pk,
        user=sc["admin"],
    )
    session_id = started["session"]["id"]
    from apps.academics.models.promotion import AcademicPromotionDecision

    AcademicPromotionDecision.objects.filter(session_id=session_id).update(
        final_action=PromotionAction.PROMOTE
    )
    prom_i.approve_promotion(
        branch_id=sc["branch"].pk,
        session_id=session_id,
        user=sc["admin"],
    )
    return {**sc, "session_id": session_id}


@pytest.fixture
def admin_client(approved_session):
    c = APIClient()
    c.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_access_token(approved_session['admin'])}"
    )
    return c


def test_start_preparation_seeds_mappings(approved_session):
    sid = approved_session["session_id"]
    prep_i.start_preparation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    mappings = prep_i.list_class_mappings(
        branch_id=approved_session["branch"].pk, session_id=sid
    )
    assert len(mappings["mappings"]) >= 1


def test_start_preparation_provisions_target_sections(approved_session):
    """Target-year batches are created from source sections when missing."""
    sid = approved_session["session_id"]
    sc = approved_session
    # Simulate CMR: target year exists but has no sections yet.
    Batch.objects.filter(course=sc["c2"], academic_year=sc["target"]).delete()

    prep_i.start_preparation(
        branch_id=sc["branch"].pk,
        session_id=sid,
        user=sc["admin"],
    )
    mappings = prep_i.list_class_mappings(branch_id=sc["branch"].pk, session_id=sid)
    assert mappings["mappings"][0]["targetBatchCount"] >= 1
    assert "A" in mappings["mappings"][0]["targetSections"]

    from apps.academics.models.promotion import AcademicPromotionDecision

    decision = AcademicPromotionDecision.objects.get(session_id=sid)
    assert decision.target_batch_id is not None
    assert Batch.objects.filter(course=sc["c2"], academic_year=sc["target"], name="A").exists()


def test_validate_classifies_ready(approved_session):
    sid = approved_session["session_id"]
    prep_i.start_preparation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    result = val_i.run_validation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    assert result["students"]["ready"] >= 1
    assert "executionImpact" in result
    assert result["executionImpact"]["studentsPromoted"] >= 1
    assert len(result["sampleStudents"]) >= 1


def test_blocked_when_missing_fee_structure(approved_session):
    sid = approved_session["session_id"]
    FeeStructure.objects.filter(batch=approved_session["batch2_target"]).delete()
    prep_i.start_preparation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    result = val_i.run_validation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    assert result["students"]["blocked"] >= 1
    assert result["canLock"] is False


def test_lock_rejected_when_blocked(approved_session):
    sid = approved_session["session_id"]
    FeeStructure.objects.filter(batch=approved_session["batch2_target"]).delete()
    prep_i.start_preparation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    val_i.run_validation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    with pytest.raises(Exception):
        prep_i.lock_preparation(
            branch_id=approved_session["branch"].pk,
            session_id=sid,
            user=approved_session["admin"],
        )


def test_validation_unblocks_after_published_fee_without_target_enrollments(approved_session):
    """Published fee on an empty target-year section satisfies promotion validation."""
    from apps.academics.interactors.promotion_validation import BLOCK_MISSING_FEE
    from apps.admissions.queries.enrollment import enrollments_in_batch

    sid = approved_session["session_id"]
    sc = approved_session
    FeeStructure.objects.filter(batch=sc["batch2_target"]).delete()

    prep_i.start_preparation(
        branch_id=sc["branch"].pk,
        session_id=sid,
        user=sc["admin"],
    )
    blocked = val_i.run_validation(
        branch_id=sc["branch"].pk,
        session_id=sid,
        user=sc["admin"],
    )
    assert blocked["students"]["blocked"] >= 1
    assert blocked["students"]["blockedByReason"].get(BLOCK_MISSING_FEE, 0) >= 1
    assert enrollments_in_batch(sc["batch2_target"].id).count() == 0

    FeeStructure.objects.create(
        branch=sc["branch"],
        batch=sc["batch2_target"],
        academic_year=sc["target"],
        name="Year 2 Fee Structure",
        components=[
            {"kind": "tuition", "label": "Tuition", "amount_paise": 5000000, "installment_no": 1, "due_date": "2025-06-01"},
        ],
        status=FeeStructureStatus.PUBLISHED,
    )

    ready = val_i.run_validation(
        branch_id=sc["branch"].pk,
        session_id=sid,
        user=sc["admin"],
    )
    assert ready["students"]["ready"] >= 1
    assert ready["students"]["blockedByReason"].get(BLOCK_MISSING_FEE, 0) == 0


def test_lock_and_unlock_preparation(approved_session):
    sid = approved_session["session_id"]
    prep_i.start_preparation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    val_i.run_validation(branch_id=approved_session["branch"].pk, session_id=sid, user=approved_session["admin"])
    state = prep_i.lock_preparation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    assert state["preparationStatus"] == PreparationStatus.LOCKED

    enr_before = StudentEnrollment.objects.count()
    prep_i.unlock_preparation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        reason="Need to adjust section mappings before execution.",
        user=approved_session["admin"],
    )
    assert StudentEnrollment.objects.count() == enr_before


def test_stale_after_fee_structure_change(approved_session):
    sid = approved_session["session_id"]
    prep_i.start_preparation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    val_i.run_validation(branch_id=approved_session["branch"].pk, session_id=sid, user=approved_session["admin"])
    prep_i.lock_preparation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    fs = FeeStructure.objects.get(batch=approved_session["batch2_target"])
    fs.version += 1
    fs.save(update_fields=["version", "updated_at"])

    preview = val_i.get_preview(branch_id=approved_session["branch"].pk, session_id=sid)
    assert preview["isStale"] is True


def test_preparation_api_start(admin_client, approved_session):
    sid = approved_session["session_id"]
    resp = admin_client.post(reverse("academics:promotion-preparation-start", args=[sid]))
    assert resp.status_code == 200


def test_validate_no_enrollment_side_effects(approved_session):
    sid = approved_session["session_id"]
    count_before = StudentEnrollment.objects.count()
    prep_i.start_preparation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    val_i.run_validation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    prep_i.lock_preparation(
        branch_id=approved_session["branch"].pk,
        session_id=sid,
        user=approved_session["admin"],
    )
    assert StudentEnrollment.objects.count() == count_before


def test_outstanding_fees_check_includes_student_detail(approved_session, college_scenario):
    sid = approved_session["session_id"]
    sc = college_scenario
    enrollment = StudentEnrollment.objects.get(
        student_profile=sc["profile"],
        academic_year=sc["year"],
    )
    FeeInvoice.objects.create(
        branch=sc["branch"],
        student=enrollment,
        total_paise=500_000,
        paid_paise=100_000,
        status=InvoiceStatus.PARTIAL,
    )
    prep_i.start_preparation(
        branch_id=sc["branch"].pk,
        session_id=sid,
        user=sc["admin"],
    )
    result = val_i.run_validation(
        branch_id=sc["branch"].pk,
        session_id=sid,
        user=sc["admin"],
    )
    outstanding = next(c for c in result["checks"] if c["id"] == "outstanding_fees")
    assert outstanding["status"] == "warning"
    assert outstanding["issueCount"] == 1
    assert outstanding["issues"][0]["outstandingPaise"] == 400_000
    assert outstanding["totalOutstandingPaise"] == 400_000
    assert outstanding["issues"][0]["studentName"]
    assert "₹4,000.00" in outstanding["message"]
    assert result["executionImpact"]["outstandingBalancesToCarryForward"] == 1
    assert result["executionImpact"]["totalOutstandingPaise"] == 400_000
