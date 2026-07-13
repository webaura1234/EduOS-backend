"""Phase 3 — promotion execution."""

import datetime
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.interactors import promotion as prom_i
from apps.academics.interactors import promotion_execution as exec_i
from apps.academics.interactors import promotion_preparation as prep_i
from apps.academics.interactors import promotion_validation as val_i
from apps.academics.queries import promotion_preparation as prep_q
from apps.academics.models import AcademicPeriod, AcademicYear, Batch, Course, Department
from apps.academics.models.promotion import (
    AcademicPromotionDecision,
    AcademicPromotionSession,
    ExecutionReadiness,
    PreparationStatus,
    PromotionAction,
    PromotionExecutionStatus,
)
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.enums import EnrollmentStatus
from apps.admissions.models import StudentEnrollment
from apps.communications.models import Notification
from apps.fees.enums import FeeStructureStatus
from apps.fees.models import FeeStructure
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def locked_session():
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
        custom_login_id="STU-EX",
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

    started = prom_i.start_promotion(
        branch=branch,
        tenant=tenant,
        source_year_id=year.pk,
        target_year_id=target.pk,
        user=admin,
    )
    session_id = started["session"]["id"]
    from apps.academics.models.promotion import AcademicPromotionDecision

    AcademicPromotionDecision.objects.filter(session_id=session_id).update(
        final_action=PromotionAction.PROMOTE
    )
    prom_i.approve_promotion(branch_id=branch.pk, session_id=session_id, user=admin)
    prep_i.start_preparation(branch_id=branch.pk, session_id=session_id, user=admin)
    val_i.run_validation(branch_id=branch.pk, session_id=session_id, user=admin)
    prep_i.lock_preparation(branch_id=branch.pk, session_id=session_id, user=admin)

    return {
        "branch": branch,
        "tenant": tenant,
        "year": year,
        "target": target,
        "admin": admin,
        "profile": profile,
        "session_id": session_id,
    }


@pytest.fixture
def admin_client(locked_session):
    c = APIClient()
    c.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_access_token(locked_session['admin'])}"
    )
    return c


def test_dry_run_returns_summary(locked_session):
    dry = exec_i.get_dry_run(
        branch_id=locked_session["branch"].pk,
        session_id=locked_session["session_id"],
    )
    assert dry["canExecute"] is True
    assert dry["students"]["ready"] >= 1
    assert dry["students"]["blocked"] == 0
    assert dry["confirmationPhrase"] == "PROMOTE 2025-26"
    assert dry["confirmToken"]
    assert dry["willRunInBackground"] is True


def test_execute_rejects_wrong_confirmation(locked_session):
    sc = locked_session
    dry = exec_i.get_dry_run(branch_id=sc["branch"].pk, session_id=sc["session_id"])
    with pytest.raises(Exception):
        exec_i.start_execution(
            branch_id=sc["branch"].pk,
            session_id=sc["session_id"],
            confirmation_phrase_input="WRONG",
            confirm_token=dry["confirmToken"],
            user=sc["admin"],
        )


def test_execute_and_run_sync(locked_session):
    sc = locked_session
    dry = exec_i.get_dry_run(branch_id=sc["branch"].pk, session_id=sc["session_id"])
    started = exec_i.start_execution(
        branch_id=sc["branch"].pk,
        session_id=sc["session_id"],
        confirmation_phrase_input="PROMOTE 2025-26",
        confirm_token=dry["confirmToken"],
        user=sc["admin"],
    )
    assert started["status"] == PromotionExecutionStatus.RUNNING

    from apps.academics.models.promotion import AcademicPromotionSession

    session = AcademicPromotionSession.objects.get(pk=sc["session_id"])
    session.refresh_from_db()
    assert session.execution_status in (
        PromotionExecutionStatus.SUCCEEDED,
        PromotionExecutionStatus.PARTIAL,
        PromotionExecutionStatus.RUNNING,
    )

    sc["target"].refresh_from_db()
    sc["year"].refresh_from_db()
    assert sc["target"].is_current is True
    assert sc["year"].is_frozen is True

    target_enr = StudentEnrollment.objects.filter(
        student_profile=sc["profile"],
        academic_year=sc["target"],
        is_active=True,
    )
    assert target_enr.exists()


def test_dry_run_api(admin_client, locked_session):
    sid = locked_session["session_id"]
    resp = admin_client.get(reverse("academics:promotion-execute-dry-run", args=[sid]))
    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)
    assert data["confirmationPhrase"] == "PROMOTE 2025-26"
    assert data.get("confirmToken")


def test_execute_rejects_stale_confirm_token(locked_session):
    sc = locked_session
    dry = exec_i.get_dry_run(branch_id=sc["branch"].pk, session_id=sc["session_id"])
    stale_token = dry["confirmToken"]

    prep_i.unlock_preparation(
        branch_id=sc["branch"].pk,
        session_id=sc["session_id"],
        reason="Need to adjust mappings before final execution run.",
        user=sc["admin"],
    )
    fs = FeeStructure.objects.filter(academic_year=sc["target"]).first()
    assert fs is not None
    fs.version += 1
    fs.save(update_fields=["version", "updated_at"])
    val_i.run_validation(
        branch_id=sc["branch"].pk,
        session_id=sc["session_id"],
        user=sc["admin"],
    )
    prep_i.lock_preparation(
        branch_id=sc["branch"].pk,
        session_id=sc["session_id"],
        user=sc["admin"],
    )
    fresh = exec_i.get_dry_run(branch_id=sc["branch"].pk, session_id=sc["session_id"])
    assert fresh["confirmToken"] != stale_token

    with pytest.raises(Exception):
        exec_i.start_execution(
            branch_id=sc["branch"].pk,
            session_id=sc["session_id"],
            confirmation_phrase_input="PROMOTE 2025-26",
            confirm_token=stale_token,
            user=sc["admin"],
        )


def test_execute_rejected_when_blocked(locked_session):
    sc = locked_session
    from apps.academics.models.promotion import AcademicPromotionSession

    session = AcademicPromotionSession.objects.get(pk=sc["session_id"])
    snap = dict(session.validation_snapshot or {})
    students = dict(snap.get("students") or {})
    students["blocked"] = 1
    snap["students"] = students
    session.validation_snapshot = snap
    session.save(update_fields=["validation_snapshot"])

    with pytest.raises(Exception):
        exec_i.start_execution(
            branch_id=sc["branch"].pk,
            session_id=sc["session_id"],
            confirmation_phrase_input="PROMOTE 2025-26",
            confirm_token=exec_i.execution_confirm_token(session),
            user=sc["admin"],
        )


def test_reopen_and_unlock_rejected_after_execution(locked_session):
    sc = locked_session
    dry = exec_i.get_dry_run(branch_id=sc["branch"].pk, session_id=sc["session_id"])
    exec_i.start_execution(
        branch_id=sc["branch"].pk,
        session_id=sc["session_id"],
        confirmation_phrase_input="PROMOTE 2025-26",
        confirm_token=dry["confirmToken"],
        user=sc["admin"],
    )
    from apps.academics.models.promotion import AcademicPromotionSession

    session = AcademicPromotionSession.objects.get(pk=sc["session_id"])
    session.refresh_from_db()
    assert session.execution_status == PromotionExecutionStatus.SUCCEEDED

    with pytest.raises(Exception):
        prom_i.reopen_promotion_review(
            branch_id=sc["branch"].pk,
            session_id=sc["session_id"],
            reason="Should not be allowed after execution completed.",
            user=sc["admin"],
        )

    with pytest.raises(Exception):
        prep_i.unlock_preparation(
            branch_id=sc["branch"].pk,
            session_id=sc["session_id"],
            reason="Should not be allowed after execution completed.",
            user=sc["admin"],
        )


def test_no_undo_promotion_api_route():
    from django.urls import get_resolver

    resolver = get_resolver()
    names = {p.name for p in resolver.url_patterns if hasattr(p, "name") and p.name}

    def walk(patterns, acc):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                walk(p.url_patterns, acc)
            elif getattr(p, "name", None):
                acc.add(p.name)

    all_names: set[str] = set()
    walk(resolver.url_patterns, all_names)
    assert not any("undo" in (n or "").lower() and "promotion" in (n or "").lower() for n in all_names)


def test_execute_returns_existing_run_when_same_session_running(locked_session):
    sc = locked_session
    from apps.academics.models.promotion import AcademicPromotionSession
    from apps.academics.queries import promotion_execution as exec_q
    from unittest.mock import patch

    session = AcademicPromotionSession.objects.get(pk=sc["session_id"])
    run = exec_q.create_run(
        session=session,
        student_total=1,
        estimated_duration_ms=30_000,
        user=sc["admin"],
    )
    prep_q.update_session(
        session,
        {"execution_status": PromotionExecutionStatus.RUNNING},
        user=sc["admin"],
    )

    dry = exec_i.get_dry_run(branch_id=sc["branch"].pk, session_id=sc["session_id"])
    with patch("apps.academics.tasks.execute_promotion_task.delay"):
        second = exec_i.start_execution(
            branch_id=sc["branch"].pk,
            session_id=sc["session_id"],
            confirmation_phrase_input="PROMOTE 2025-26",
            confirm_token=dry["confirmToken"],
            user=sc["admin"],
        )

    assert second["runId"] == str(run.pk)
    from apps.academics.models.promotion import AcademicPromotionExecutionRun

    assert AcademicPromotionExecutionRun.objects.filter(session=session).count() == 1


def _create_other_running_session(sc):
    from apps.academics.models.promotion import AcademicPromotionSession, PreparationStatus, PromotionSessionStatus

    prior_source = AcademicYear.objects.create(
        branch=sc["branch"],
        name="2023-24",
        is_current=False,
        is_frozen=True,
        start_date=datetime.date(2023, 6, 1),
        end_date=datetime.date(2024, 4, 30),
    )
    other = AcademicPromotionSession.objects.create(
        branch=sc["branch"],
        source_year=prior_source,
        target_year=sc["year"],
        status=PromotionSessionStatus.APPROVED,
        preparation_status=PreparationStatus.LOCKED,
        execution_status=PromotionExecutionStatus.RUNNING,
        created_by=sc["admin"],
        updated_by=sc["admin"],
    )
    from apps.academics.queries import promotion_execution as exec_q

    exec_q.create_run(
        session=other,
        student_total=1,
        estimated_duration_ms=30_000,
        user=sc["admin"],
    )
    return other


def test_execute_returns_409_when_other_session_running_on_branch(locked_session):
    from apps.academics.exceptions import PromotionExecutionInProgressError

    sc = locked_session
    other = _create_other_running_session(sc)
    dry = exec_i.get_dry_run(branch_id=sc["branch"].pk, session_id=sc["session_id"])

    with pytest.raises(PromotionExecutionInProgressError) as exc_info:
        exec_i.start_execution(
            branch_id=sc["branch"].pk,
            session_id=sc["session_id"],
            confirmation_phrase_input="PROMOTE 2025-26",
            confirm_token=dry["confirmToken"],
            user=sc["admin"],
        )

    assert exc_info.value.detail["runningSessionId"] == str(other.pk)


def test_execute_api_returns_409(admin_client, locked_session):
    sc = locked_session
    other = _create_other_running_session(sc)
    dry = exec_i.get_dry_run(branch_id=sc["branch"].pk, session_id=sc["session_id"])
    sid = sc["session_id"]

    resp = admin_client.post(
        reverse("academics:promotion-execute", args=[sid]),
        {
            "confirmationPhrase": "PROMOTE 2025-26",
            "confirmToken": dry["confirmToken"],
        },
        format="json",
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body.get("errors", {}).get("runningSessionId") == str(other.pk)


def test_resume_returns_409_when_other_session_running(locked_session):
    from apps.academics.exceptions import PromotionExecutionInProgressError

    sc = locked_session
    _create_other_running_session(sc)

    with pytest.raises(PromotionExecutionInProgressError):
        exec_i.resume_execution(
            branch_id=sc["branch"].pk,
            session_id=sc["session_id"],
            user=sc["admin"],
        )


@pytest.mark.parametrize(
    "action,template",
    [
        (PromotionAction.PROMOTE, "academics.promotion_completed"),
        (PromotionAction.RETAIN, "academics.promotion_retained"),
        (PromotionAction.GRADUATE, "academics.promotion_graduated"),
        (PromotionAction.TRANSFER_OUT, "academics.promotion_transferred"),
        (PromotionAction.WITHDRAWN, "academics.promotion_withdrawn"),
    ],
)
def test_notify_student_sends_for_executable_actions(locked_session, action, template):
    sc = locked_session
    session = AcademicPromotionSession.objects.get(pk=sc["session_id"])
    decision = AcademicPromotionDecision.objects.filter(session=session).first()
    decision.final_action = action
    decision.save(update_fields=["final_action", "updated_at"])

    sent, failures = exec_i._notify_student(session, decision, sc["profile"], user=sc["admin"])
    assert failures == 0
    assert sent >= 1
    assert Notification.objects.filter(
        recipient=sc["profile"].user,
        notification_type=template,
    ).exists()


def test_execute_reports_notification_failures(locked_session):
    sc = locked_session
    dry = exec_i.get_dry_run(branch_id=sc["branch"].pk, session_id=sc["session_id"])

    with patch(
        "apps.communications.interactors.create.create_notification",
        side_effect=RuntimeError("notification down"),
    ):
        exec_i.start_execution(
            branch_id=sc["branch"].pk,
            session_id=sc["session_id"],
            confirmation_phrase_input="PROMOTE 2025-26",
            confirm_token=dry["confirmToken"],
            user=sc["admin"],
        )

    session = AcademicPromotionSession.objects.get(pk=sc["session_id"])
    assert session.execution_status in (
        PromotionExecutionStatus.SUCCEEDED,
        PromotionExecutionStatus.PARTIAL,
    )
    assert session.execution_report.get("notificationFailures", 0) >= 1


def test_report_download_csv(admin_client, locked_session):
    sid = locked_session["session_id"]
    url = reverse("academics:promotion-execute-report-download", args=[sid])
    resp = admin_client.get(url)
    assert resp.status_code == 200
    assert "text/csv" in resp["Content-Type"]


def test_report_download_pdf_success(admin_client, locked_session):
    sid = locked_session["session_id"]
    url = reverse("academics:promotion-execute-report-download", args=[sid])
    fake_pdf = b"%PDF-1.4 promotion report"

    with patch("apps.core.exports.pdf.render_pdf", return_value=fake_pdf):
        resp = admin_client.get(url, {"format": "pdf"})

    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")
    assert "promotion-report.pdf" in resp["Content-Disposition"]


def test_report_download_pdf_failure_returns_503(admin_client, locked_session):
    from apps.core.exports.pdf import PdfRenderError

    sid = locked_session["session_id"]
    url = reverse("academics:promotion-execute-report-download", args=[sid])

    with patch(
        "apps.core.exports.pdf.render_pdf",
        side_effect=PdfRenderError("weasyprint unavailable"),
    ):
        resp = admin_client.get(url, {"format": "pdf"})

    assert resp.status_code == 503
    body = resp.json()
    data = body.get("data", body)
    assert data["error"] == "pdf_unavailable"
    assert data["fallbackFormat"] == "csv"
