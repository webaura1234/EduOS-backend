"""Notification center MVP — templates, inbox, triggers, expiration, permissions."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory, DepartmentFactory
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.communications.interactors.create import create_notification
from apps.communications.interactors.triggers.fees import run_fee_notification_scan
from apps.communications.models import Notification, NotificationPreference
from apps.communications.queries import inbox as inbox_q
from apps.communications.queries import notification as pref_q
from apps.communications.templates.registry import TEMPLATES
from apps.communications.templates.render import render_notification
from apps.fees.tests.factories import FeeInvoiceFactory
from apps.organizations.models import TenantSettings
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch,
        phone="+919810000001", custom_login_id=None, must_change_password=False,
    )
    student = UserFactory(
        role=Role.STUDENT, tenant=tenant, branch=branch,
        custom_login_id="STU-1", must_change_password=False,
    )
    profile = StudentProfile.objects.create(user=student, current_batch=batch)
    enrollment = StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)
    TenantSettings.objects.get_or_create(
        tenant=tenant,
        defaults={"fee_reminder_days": [7, 3, 1]},
    )
    return dict(
        tenant=tenant, branch=branch, admin=admin, student=student,
        batch=batch, enrollment=enrollment, profile=profile,
    )


@pytest.mark.parametrize("notification_type", list(TEMPLATES.keys()))
def test_templates_render_with_required_vars(env, notification_type):
    user = env["student"]
    variables = {
        "student_name": "Asha",
        "amount_due": "5,000",
        "amount_paid": "5,000",
        "due_date": "2026-08-01",
        "days_until_due": "3",
        "days_overdue": "2",
        "receipt_ref": "RCPT-1",
        "date": "2026-07-01",
        "class_label": "10-A",
        "attendance_percent": "70",
        "threshold_percent": "75",
        "exam_name": "Mid Term",
        "exam_id": "exam-1",
        "applicant_name": "Ravi",
        "application_number": "APP-001",
        "new_status": "approved",
        "application_id": "app-1",
        "title": "Holiday notice",
        "announcement_id": "ann-1",
        "body_preview": "School closed tomorrow.",
    }
    rendered = render_notification(notification_type, user, variables)
    assert rendered["title"]
    assert rendered["message"]
    assert rendered["action_url"].startswith("/")


def test_template_missing_variable_raises(env):
    with pytest.raises(ValidationError):
        render_notification("fee.due_reminder", env["student"], {"student_name": "A"})


def test_create_notification_dedup(env):
    row = create_notification(
        "fee.due_today",
        tenant=env["tenant"],
        branch=env["branch"],
        recipient=env["student"],
        variables={
            "student_name": env["student"].full_name,
            "amount_due": "1,000",
            "due_date": timezone.localdate().isoformat(),
        },
        dedup_key="test:dedup:1",
        due_date=timezone.localdate(),
    )
    assert row is not None
    again = create_notification(
        "fee.due_today",
        tenant=env["tenant"],
        branch=env["branch"],
        recipient=env["student"],
        variables={
            "student_name": env["student"].full_name,
            "amount_due": "1,000",
            "due_date": timezone.localdate().isoformat(),
        },
        dedup_key="test:dedup:1",
        due_date=timezone.localdate(),
    )
    assert again is None
    assert Notification.objects.filter(recipient=env["student"]).count() == 1


def test_in_app_pref_gate(env):
    pref = pref_q.get_or_create_preference(env["student"])
    pref.in_app = False
    pref.save(update_fields=["in_app"])
    row = create_notification(
        "fee.due_today",
        tenant=env["tenant"],
        branch=env["branch"],
        recipient=env["student"],
        variables={
            "student_name": env["student"].full_name,
            "amount_due": "1,000",
            "due_date": timezone.localdate().isoformat(),
        },
        dedup_key="test:pref:off",
        due_date=timezone.localdate(),
    )
    assert row is None


def test_expired_notifications_excluded_from_inbox(env):
    create_notification(
        "attendance.absent",
        tenant=env["tenant"],
        branch=env["branch"],
        recipient=env["student"],
        variables={
            "student_name": env["student"].full_name,
            "date": "2026-07-01",
            "class_label": "10-A",
        },
        dedup_key="test:expired",
    )
    Notification.objects.filter(recipient=env["student"]).update(
        expires_at=timezone.now() - timedelta(hours=1),
    )
    assert list(inbox_q.list_for_recipient(env["student"].pk)) == []
    assert inbox_q.unread_count(env["student"].pk) == 0


def test_inbox_api_list_and_mark_read(env):
    create_notification(
        "announcement.published",
        tenant=env["tenant"],
        branch=env["branch"],
        recipient=env["student"],
        variables={
            "title": "Test",
            "announcement_id": "a1",
            "body_preview": "Body",
        },
        dedup_key="test:inbox:1",
    )
    list_url = reverse("communications:notifications")
    unread_url = reverse("communications:notifications-unread-count")
    mark_all_url = reverse("communications:notifications-mark-all-read")

    resp = _client(env["student"]).get(list_url)
    assert resp.status_code == 200
    payload = _data(resp)
    assert payload["unreadCount"] == 1
    assert len(payload["notifications"]) == 1
    assert payload["notifications"][0]["actionUrl"]

    assert _data(_client(env["student"]).get(unread_url))["unreadCount"] == 1

    nid = payload["notifications"][0]["id"]
    mark_url = reverse("communications:notification-mark-read", args=[nid])
    assert _client(env["student"]).patch(mark_url).status_code == 200
    assert _data(_client(env["student"]).get(unread_url))["unreadCount"] == 0

    create_notification(
        "announcement.published",
        tenant=env["tenant"],
        branch=env["branch"],
        recipient=env["student"],
        variables={"title": "T2", "announcement_id": "a2", "body_preview": "B2"},
        dedup_key="test:inbox:2",
    )
    assert _client(env["student"]).post(mark_all_url).status_code == 200
    assert _data(_client(env["student"]).get(unread_url))["unreadCount"] == 0


def test_branch_recent_admin_only(env):
    create_notification(
        "announcement.published",
        tenant=env["tenant"],
        branch=env["branch"],
        recipient=env["student"],
        variables={"title": "Branch", "announcement_id": "b1", "body_preview": "x"},
        dedup_key="test:branch:1",
    )
    url = reverse("communications:notifications-branch-recent")
    assert _client(env["admin"]).get(url).status_code == 200
    assert len(_data(_client(env["admin"]).get(url))["notifications"]) >= 1
    assert _client(env["student"]).get(url).status_code == 403


def test_fee_reminder_days_respected(env):
    settings = TenantSettings.objects.get(tenant=env["tenant"])
    settings.fee_reminder_days = [7, 3]
    settings.save(update_fields=["fee_reminder_days"])

    today = timezone.localdate()
    due = today + timedelta(days=3)
    FeeInvoiceFactory(
        branch=env["branch"],
        student=env["enrollment"],
        due_date=due,
        total_paise=500000,
        paid_paise=0,
    )
    due5 = today + timedelta(days=5)
    FeeInvoiceFactory(
        branch=env["branch"],
        student=env["enrollment"],
        due_date=due5,
        total_paise=300000,
        paid_paise=0,
    )

    count = run_fee_notification_scan()
    assert count >= 1
    types = set(
        Notification.objects.filter(recipient=env["student"]).values_list("notification_type", flat=True)
    )
    assert "fee.due_reminder" in types


def test_payment_expires_fee_reminders(env):
    due = timezone.localdate() + timedelta(days=3)
    invoice = FeeInvoiceFactory(
        branch=env["branch"],
        student=env["enrollment"],
        due_date=due,
        total_paise=500000,
        paid_paise=0,
    )
    create_notification(
        "fee.due_reminder",
        tenant=env["tenant"],
        branch=env["branch"],
        recipient=env["student"],
        variables={
            "student_name": env["student"].full_name,
            "amount_due": "5,000",
            "due_date": due.isoformat(),
            "days_until_due": "3",
        },
        dedup_key=f"fee:due_reminder:{invoice.pk}:3",
        related_entity_type="invoice",
        related_entity_id=invoice.pk,
        due_date=due,
    )
    assert inbox_q.unread_count(env["student"].pk) == 1
    inbox_q.expire_fee_notifications_for_invoice(invoice.pk)
    assert inbox_q.unread_count(env["student"].pk) == 0


def test_announcement_post_emits_notifications(env):
    url = reverse("communications:announcements")
    resp = _client(env["admin"]).post(url, {
        "title": "Sports day",
        "body": "Bring your kit",
        "targetType": "all",
        "channels": ["in_app"],
    }, format="json")
    assert resp.status_code == 201
    assert Notification.objects.filter(
        recipient=env["student"],
        notification_type="announcement.published",
    ).exists()


def test_invalid_target_type_rejected(env):
    url = reverse("communications:announcements")
    resp = _client(env["admin"]).post(url, {
        "title": "Bad target",
        "body": "x",
        "targetType": "invalid",
        "channels": ["in_app"],
    }, format="json")
    assert resp.status_code == 400


def test_department_targeting_for_student(env):
    dept = DepartmentFactory(branch=env["branch"])
    batch = BatchFactory(
        course__department=dept,
        academic_year=env["batch"].academic_year,
    )
    other_batch = env["batch"]
    student2 = UserFactory(
        role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
        custom_login_id="STU-2", must_change_password=False,
    )
    profile2 = StudentProfile.objects.create(user=student2, current_batch=batch)
    StudentEnrollmentFactory(student_profile=profile2, branch=env["branch"], batch=batch)

    admin = _client(env["admin"])
    url = reverse("communications:announcements")
    admin.post(url, {
        "title": "Dept only",
        "body": "For dept students",
        "targetType": "department",
        "targetValue": str(dept.id),
        "channels": ["in_app"],
    }, format="json")
    admin.post(url, {
        "title": "Other batch",
        "body": "Other",
        "targetType": "batch",
        "targetValue": str(other_batch.id),
        "channels": ["in_app"],
    }, format="json")

    feed = _data(_client(student2).get(reverse("communications:student-announcements")))
    titles = {a["title"] for a in feed["announcements"]}
    assert "Dept only" in titles
    assert "Other batch" not in titles

    feed_main = _data(_client(env["student"]).get(reverse("communications:student-announcements")))
    main_titles = {a["title"] for a in feed_main["announcements"]}
    assert "Dept only" not in main_titles
    assert "Other batch" in main_titles
