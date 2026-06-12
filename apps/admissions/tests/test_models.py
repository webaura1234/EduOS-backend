import pytest
from django.db import IntegrityError
from apps.admissions.tests.factories import EnquiryFactory, ApplicationFactory, ApplicationDocumentFactory, WaitlistFactory, StudentEnrollmentFactory

pytestmark = pytest.mark.django_db


def test_enquiry_creation():
    enquiry = EnquiryFactory()
    assert enquiry.applicant_name.startswith("Applicant")
    assert enquiry.status == "new"


def test_application_creation():
    app = ApplicationFactory()
    assert app.status == "draft"
    assert app.enquiry is not None


def test_application_document_creation():
    doc = ApplicationDocumentFactory()
    assert doc.doc_type == "Aadhar Card"
    assert doc.verification_status == "pending"


def test_waitlist_creation():
    wl = WaitlistFactory()
    assert wl.rank > 0


def test_enrollment_unique_constraint():
    enr1 = StudentEnrollmentFactory()
    # Attempting to create another enrollment for same profile and academic year should fail due to uniqueness constraint
    with pytest.raises(IntegrityError):
        StudentEnrollmentFactory(
            student_profile=enr1.student_profile,
            academic_year=enr1.academic_year,
            branch=enr1.branch,
            batch=enr1.batch
        )
