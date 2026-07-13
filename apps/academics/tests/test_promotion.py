"""Academic year promotion workspace — Phase 1 (decisions only)."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.interactors import promotion as prom_i
from apps.academics.interactors import promotion_recommendations as rec_i
from apps.academics.models import AcademicPeriod, AcademicYear, Batch, Course, Department
from apps.academics.models.promotion import (
    AcademicPromotionSession,
    PromotionAction,
    PromotionSessionStatus,
)
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.enums import EnrollmentStatus
from apps.admissions.models import StudentEnrollment
from apps.analytics.models import AuditLog
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def _resolve_all_decisions(admin_client, session_id, *, final_action="promote"):
    decisions = _data(admin_client.get(reverse("academics:promotion-decisions", args=[session_id])))[
        "decisions"
    ]
    ids = [d["id"] for d in decisions]
    admin_client.patch(
        reverse("academics:promotion-decision-bulk-override", args=[session_id]),
        {
            "finalAction": final_action,
            "reason": "Committee resolved all students before approval.",
            "decisionIds": ids,
        },
        format="json",
    )


def _approve_resolved(admin_client, session_id):
    _resolve_all_decisions(admin_client, session_id)
    return admin_client.post(reverse("academics:promotion-approve", args=[session_id]))


@pytest.fixture
def school_scenario():
    tenant = TenantFactory(institution_type="school")
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
    dept = Department.objects.create(branch=branch, name="Science", department_type="stream")
    c9 = Course.objects.create(department=dept, name="Grade 09")
    Course.objects.create(department=dept, name="Grade 10")
    batch9 = Batch.objects.create(course=c9, academic_year=year, name="A", capacity=40)

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
        custom_login_id="STU-P1",
        must_change_password=False,
    )
    profile = StudentProfile.objects.create(
        user=student, current_batch=batch9, academic_status=AcademicStatus.ACTIVE
    )
    StudentEnrollment.objects.create(
        student_profile=profile,
        batch=batch9,
        academic_year=year,
        branch=branch,
        status=EnrollmentStatus.ACTIVE,
    )

    return {
        "tenant": tenant,
        "branch": branch,
        "year": year,
        "target": target,
        "batch9": batch9,
        "student": student,
        "profile": profile,
        "admin": admin,
    }


@pytest.fixture
def admin_client(school_scenario):
    c = APIClient()
    c.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_access_token(school_scenario['admin'])}"
    )
    return c


def test_school_non_final_recommends_manual_review(school_scenario):
    rec = rec_i.recommend_for_student(
        profile=school_scenario["profile"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
    )
    assert rec.action == PromotionAction.MANUAL_REVIEW
    assert rec.reason_label == "Student requires manual review"
    assert rec.reason_code == "no_yearly_pass_fail_policy"


def test_missing_batch_recommends_pending(school_scenario):
    profile = school_scenario["profile"]
    profile.current_batch = None
    profile.save(update_fields=["current_batch"])
    enrollment = StudentEnrollment.objects.get(
        student_profile=profile, academic_year=school_scenario["year"]
    )
    enrollment.batch = None
    enrollment.save(update_fields=["batch"])
    rec = rec_i.recommend_for_student(
        profile=profile,
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        enrollment=enrollment,
    )
    assert rec.action == PromotionAction.PENDING
    assert rec.reason_label == "No class assigned"


def test_start_creates_session_and_decisions(admin_client, school_scenario):
    resp = admin_client.post(
        reverse("academics:promotion-start"),
        {
            "sourceYearId": str(school_scenario["year"].pk),
            "targetYearId": str(school_scenario["target"].pk),
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = _data(resp)
    assert body["session"]["status"] == PromotionSessionStatus.DRAFT
    assert body["studentsAnalyzed"] == 1
    assert body["session"]["counts"]["total"] == 1
    assert body["session"]["counts"]["manualReview"] == 1


def test_start_rejects_target_year_with_end_before_start(admin_client, school_scenario):
    resp = admin_client.post(
        reverse("academics:promotion-start"),
        {
            "sourceYearId": str(school_scenario["year"].pk),
            "targetYearCreate": {
                "name": "2026-27",
                "startDate": "2026-07-15",
                "endDate": "2026-07-13",
            },
        },
        format="json",
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "endDate" in str(body.get("errors", {}))


def test_start_returns_409_when_draft_exists(admin_client, school_scenario):
    prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    resp = admin_client.post(
        reverse("academics:promotion-start"),
        {
            "sourceYearId": str(school_scenario["year"].pk),
            "targetYearId": str(school_scenario["target"].pk),
        },
        format="json",
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body.get("errors", {}).get("code") == "promotion_in_progress"


def test_get_current_returns_draft_for_resume(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    resp = admin_client.get(reverse("academics:promotion-current"))
    assert resp.status_code == 200
    body = _data(resp)
    assert body["status"] == "draft"
    assert body["session"]["id"] == started["session"]["id"]
    assert body["sourceYearLabel"] == "2024-25"
    assert body["targetYearLabel"] == "2025-26"


def test_decisions_response_has_reason_label_not_code(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    session_id = started["session"]["id"]
    resp = admin_client.get(reverse("academics:promotion-decisions", args=[session_id]))
    assert resp.status_code == 200
    row = _data(resp)["decisions"][0]
    assert "reasonLabel" in row
    assert "reasonCode" not in row
    assert row["reasonLabel"] == "Student requires manual review"


def test_override_requires_reason(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    session_id = started["session"]["id"]
    decisions = admin_client.get(reverse("academics:promotion-decisions", args=[session_id]))
    decision_id = _data(decisions)["decisions"][0]["id"]

    resp = admin_client.patch(
        reverse("academics:promotion-decision-override", args=[session_id, decision_id]),
        {"finalAction": "promote", "reason": "short"},
        format="json",
    )
    assert resp.status_code == 400


def test_override_creates_audit_log(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    session_id = started["session"]["id"]
    decisions = admin_client.get(reverse("academics:promotion-decisions", args=[session_id]))
    decision_id = _data(decisions)["decisions"][0]["id"]

    before = AuditLog.objects.filter(tenant=school_scenario["tenant"]).count()
    resp = admin_client.patch(
        reverse("academics:promotion-decision-override", args=[session_id, decision_id]),
        {"finalAction": "promote", "reason": "Passed all subjects based on term records."},
        format="json",
    )
    assert resp.status_code == 200
    assert _data(resp)["finalAction"] == "promote"
    assert _data(resp)["isOverridden"] is True
    assert AuditLog.objects.filter(tenant=school_scenario["tenant"]).count() == before + 1


def test_approve_locks_session(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    session_id = started["session"]["id"]
    decisions = admin_client.get(reverse("academics:promotion-decisions", args=[session_id]))
    decision_id = _data(decisions)["decisions"][0]["id"]

    approve = _approve_resolved(admin_client, session_id)
    assert approve.status_code == 200
    assert _data(approve)["session"]["status"] == PromotionSessionStatus.APPROVED

    override = admin_client.patch(
        reverse("academics:promotion-decision-override", args=[session_id, decision_id]),
        {"finalAction": "retain", "reason": "Should not be allowed after approve."},
        format="json",
    )
    assert override.status_code == 403

    restart = admin_client.post(
        reverse("academics:promotion-start"),
        {
            "sourceYearId": str(school_scenario["year"].pk),
            "targetYearId": str(school_scenario["target"].pk),
        },
        format="json",
    )
    assert restart.status_code == 403


def test_approve_does_not_mutate_student_data(admin_client, school_scenario):
    profile = school_scenario["profile"]
    batch_before = profile.current_batch_id
    year_count = AcademicYear.objects.filter(branch=school_scenario["branch"]).count()
    enrollment_count = StudentEnrollment.objects.count()

    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    _approve_resolved(admin_client, started["session"]["id"])

    profile.refresh_from_db()
    assert profile.current_batch_id == batch_before
    assert AcademicYear.objects.filter(branch=school_scenario["branch"]).count() == year_count
    assert StudentEnrollment.objects.count() == enrollment_count


def test_get_current_returns_approved_state(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    _approve_resolved(admin_client, started["session"]["id"])

    resp = admin_client.get(reverse("academics:promotion-current"))
    assert resp.status_code == 200
    assert _data(resp)["status"] == "approved"
    assert _data(resp)["canReopenReview"] is True


def test_reopen_review_restores_draft_and_allows_override(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    session_id = started["session"]["id"]
    decisions = admin_client.get(reverse("academics:promotion-decisions", args=[session_id]))
    decision_id = _data(decisions)["decisions"][0]["id"]

    _approve_resolved(admin_client, session_id)

    reopen = admin_client.post(
        reverse("academics:promotion-reopen-review", args=[session_id]),
        {"reason": "Need to resolve manual review students before execution."},
        format="json",
    )
    assert reopen.status_code == 200
    assert _data(reopen)["session"]["status"] == PromotionSessionStatus.DRAFT

    current = admin_client.get(reverse("academics:promotion-current"))
    assert _data(current)["status"] == "draft"

    override = admin_client.patch(
        reverse("academics:promotion-decision-override", args=[session_id, decision_id]),
        {"finalAction": "promote", "reason": "Passed all subjects based on term records."},
        format="json",
    )
    assert override.status_code == 200
    assert _data(override)["finalAction"] == "promote"


def test_reopen_review_requires_reason(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    session_id = started["session"]["id"]
    _approve_resolved(admin_client, session_id)

    resp = admin_client.post(
        reverse("academics:promotion-reopen-review", args=[session_id]),
        {"reason": "short"},
        format="json",
    )
    assert resp.status_code == 400


def test_bulk_override_by_ids_updates_all_selected(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    session_id = started["session"]["id"]
    decisions = _data(admin_client.get(
        reverse("academics:promotion-decisions", args=[session_id])
    ))["decisions"]
    ids = [d["id"] for d in decisions]

    resp = admin_client.patch(
        reverse("academics:promotion-decision-bulk-override", args=[session_id]),
        {
            "finalAction": "promote",
            "reason": "Bulk promote after committee review of results.",
            "decisionIds": ids,
        },
        format="json",
    )
    assert resp.status_code == 200
    data = _data(resp)
    assert data["updated"] == len(ids)
    assert data["counts"]["promote"] == len(ids)

    refreshed = _data(admin_client.get(
        reverse("academics:promotion-decisions", args=[session_id])
    ))["decisions"]
    assert all(d["finalAction"] == "promote" and d["isOverridden"] for d in refreshed)


def test_bulk_override_by_filter_action(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    session_id = started["session"]["id"]
    decisions = _data(admin_client.get(
        reverse("academics:promotion-decisions", args=[session_id])
    ))["decisions"]
    target_action = decisions[0]["finalAction"]
    expected = sum(1 for d in decisions if d["finalAction"] == target_action)

    resp = admin_client.patch(
        reverse("academics:promotion-decision-bulk-override", args=[session_id]),
        {
            "finalAction": "retain",
            "reason": "Bulk retain for the reviewed cohort this term.",
            "filterAction": target_action,
        },
        format="json",
    )
    assert resp.status_code == 200
    assert _data(resp)["updated"] == expected


def test_bulk_override_requires_selection(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    session_id = started["session"]["id"]

    resp = admin_client.patch(
        reverse("academics:promotion-decision-bulk-override", args=[session_id]),
        {"finalAction": "promote", "reason": "Missing any selection at all here."},
        format="json",
    )
    assert resp.status_code == 400


def test_approve_rejects_unresolved_manual_review(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    session_id = started["session"]["id"]
    resp = admin_client.post(reverse("academics:promotion-approve", args=[session_id]))
    assert resp.status_code == 400


def test_bulk_override_blocked_after_approve(admin_client, school_scenario):
    started = prom_i.start_promotion(
        branch=school_scenario["branch"],
        tenant=school_scenario["tenant"],
        source_year_id=school_scenario["year"].pk,
        target_year_id=school_scenario["target"].pk,
        user=school_scenario["admin"],
    )
    session_id = started["session"]["id"]
    decisions = _data(admin_client.get(
        reverse("academics:promotion-decisions", args=[session_id])
    ))["decisions"]
    ids = [d["id"] for d in decisions]
    _approve_resolved(admin_client, session_id)

    resp = admin_client.patch(
        reverse("academics:promotion-decision-bulk-override", args=[session_id]),
        {
            "finalAction": "promote",
            "reason": "Should be rejected because session is approved.",
            "decisionIds": ids,
        },
        format="json",
    )
    assert resp.status_code == 403
