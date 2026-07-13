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


def test_enrollment_unique_constraint_active_only():
    enr1 = StudentEnrollmentFactory()
    with pytest.raises(IntegrityError):
        StudentEnrollmentFactory(
            student_profile=enr1.student_profile,
            academic_year=enr1.academic_year,
            branch=enr1.branch,
            batch=enr1.batch,
        )


def test_inactive_enrollment_allows_new_active_same_year():
    enr1 = StudentEnrollmentFactory()
    enr1.is_active = False
    enr1.save(update_fields=["is_active", "updated_at"])
    enr2 = StudentEnrollmentFactory(
        student_profile=enr1.student_profile,
        academic_year=enr1.academic_year,
        branch=enr1.branch,
        batch=enr1.batch,
    )
    assert enr2.is_active is True
    assert enr2.pk != enr1.pk
