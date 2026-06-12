import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.tests.factories import (
    EnquiryFactory,
    ApplicationFactory,
    ApplicationDocumentFactory,
    WaitlistFactory,
    StudentEnrollmentFactory,
)
from apps.academics.tests.factories import BatchFactory, AcademicYearFactory, CourseFactory
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
    tenant = TenantFactory()
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        must_change_password=False,
    )
    course = CourseFactory(department__branch=branch)
    batch = BatchFactory(course=course)
    return {
        "tenant": tenant,
        "branch": branch,
        "admin": admin,
        "course": course,
        "batch": batch,
    }


def test_enquiry_views(env):
    client = _client(env["admin"])
    
    # Create enquiry
    resp = client.post(
        reverse("admissions:enquiry-list-create"),
        {
            "source": "online",
            "applicantName": "John Doe",
            "phone": "+919876543211",
            "email": "john@example.com",
            "courseId": str(env["course"].pk),
        },
        format="json"
    )
    assert resp.status_code == 201, resp.content
    enquiry_id = _data(resp)["enquiry"]["id"]
    
    # List
    resp = client.get(reverse("admissions:enquiry-list-create"))
    assert resp.status_code == 200
    assert len(_data(resp)["enquiries"]) == 1
    
    # Detail update
    resp = client.patch(
        reverse("admissions:enquiry-detail", kwargs={"enquiry_id": enquiry_id}),
        {"notes": "Followed up"},
        format="json"
    )
    assert resp.status_code == 200
    assert _data(resp)["enquiry"]["notes"] == "Followed up"
    
    # Convert
    resp = client.post(
        reverse("admissions:enquiry-convert", kwargs={"enquiry_id": enquiry_id}),
        format="json"
    )
    assert resp.status_code == 201
    assert "application" in _data(resp)


def test_application_views(env):
    client = _client(env["admin"])
    app = ApplicationFactory(branch=env["branch"])
    
    # List
    resp = client.get(reverse("admissions:application-list"))
    assert resp.status_code == 200
    
    # Detail
    resp = client.get(reverse("admissions:application-detail", kwargs={"application_id": str(app.pk)}))
    assert resp.status_code == 200
    
    # Step save
    resp = client.patch(
        reverse("admissions:application-step", kwargs={"application_id": str(app.pk)}),
        {"step": {"step": 2}},
        format="json"
    )
    assert resp.status_code == 200
    
    # Add document
    resp = client.post(
        reverse("admissions:application-documents", kwargs={"application_id": str(app.pk)}),
        {"docType": "Passport", "s3Key": "passport.pdf"},
        format="json"
    )
    assert resp.status_code == 201
    doc_id = _data(resp)["document"]["id"]
    
    # Verify document
    resp = client.patch(
        reverse("admissions:document-verify", kwargs={"document_id": doc_id}),
        {"verificationStatus": "verified"},
        format="json"
    )
    assert resp.status_code == 200
    
    # Reject
    resp = client.post(
        reverse("admissions:application-reject", kwargs={"application_id": str(app.pk)}),
        {"rejectionReason": "Docs fake"},
        format="json"
    )
    assert resp.status_code == 200
    assert _data(resp)["application"]["status"] == "rejected"


def test_waitlist_views(env):
    client = _client(env["admin"])
    app = ApplicationFactory(branch=env["branch"])
    
    # Add to waitlist
    resp = client.post(
        reverse("admissions:waitlist-list-create"),
        {"applicationId": str(app.pk), "rank": 1},
        format="json"
    )
    assert resp.status_code == 201
    waitlist_id = _data(resp)["waitlist"]["id"]
    
    # List waitlist
    resp = client.get(reverse("admissions:waitlist-list-create"))
    assert resp.status_code == 200
    assert len(_data(resp)["waitlist"]) == 1
    
    # Course merit list
    resp = client.get(reverse("admissions:course-merit-list", kwargs={"course_id": str(app.course.pk)}))
    assert resp.status_code == 200
    
    # Promote
    resp = client.post(
        reverse("admissions:waitlist-promote", kwargs={"waitlist_id": waitlist_id}),
        format="json"
    )
    assert resp.status_code == 200
    assert _data(resp)["application"]["status"] == "accepted"


def test_enrollment_views(env):
    client = _client(env["admin"])
    enr = StudentEnrollmentFactory(branch=env["branch"])
    
    # List
    resp = client.get(reverse("admissions:enrollment-list-create"))
    assert resp.status_code == 200
    
    # Detail
    resp = client.get(reverse("admissions:enrollment-detail", kwargs={"enrollment_id": str(enr.pk)}))
    assert resp.status_code == 200
    
    # Sibling override
    other_enr = StudentEnrollmentFactory(branch=env["branch"])
    resp = client.post(
        reverse("admissions:sibling-override"),
        {"siblingStudentProfileId": str(other_enr.student_profile.pk)},
        format="json"
    )
    assert resp.status_code == 200
    assert "siblingGroupId" in _data(resp)
    
    # Transfer
    to_branch = BranchFactory(tenant=env["tenant"])
    to_batch = BatchFactory(course__department__branch=to_branch)
    resp = client.post(
        reverse("admissions:enrollment-transfer", kwargs={"enrollment_id": str(enr.pk)}),
        {
            "toBranchId": str(to_branch.pk),
            "toBatchId": str(to_batch.pk),
            "academicYearId": str(to_batch.academic_year.pk)
        },
        format="json"
    )
    assert resp.status_code == 200
    assert _data(resp)["enrollment"]["branchId"] == str(to_branch.pk)


def test_funnel_analytics_view(env):
    client = _client(env["admin"])
    EnquiryFactory(branch=env["branch"])
    
    resp = client.get(reverse("admissions:funnel-analytics"))
    assert resp.status_code == 200
    assert "bySource" in _data(resp)
