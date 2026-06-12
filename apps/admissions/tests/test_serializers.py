import pytest
from apps.admissions.serializers.enquiry import EnquirySerializer, CreateEnquirySerializer
from apps.admissions.serializers.application import ApplicationSerializer, SaveApplicationStepSerializer
from apps.admissions.serializers.enrollment import StudentEnrollmentSerializer, ProvisionEnrollmentSerializer
from apps.admissions.tests.factories import EnquiryFactory, ApplicationFactory, StudentEnrollmentFactory

pytestmark = pytest.mark.django_db


def test_enquiry_serializers():
    enquiry = EnquiryFactory()
    data = EnquirySerializer(enquiry).data
    assert data["applicantName"] == enquiry.applicant_name
    assert data["source"] == enquiry.source
    
    # Create validation
    create_ser = CreateEnquirySerializer(data={
        "source": "online",
        "applicantName": "John Doe",
    })
    assert create_ser.is_valid(), create_ser.errors


def test_application_serializers():
    app = ApplicationFactory()
    data = ApplicationSerializer(app).data
    assert data["status"] == app.status
    
    # Save step validation
    step_ser = SaveApplicationStepSerializer(data={
        "step": {"step": 3}
    })
    assert step_ser.is_valid(), step_ser.errors


def test_enrollment_serializers():
    enr = StudentEnrollmentFactory()
    data = StudentEnrollmentSerializer(enr).data
    assert data["status"] == enr.status
    
    # Provision validation
    prov_ser = ProvisionEnrollmentSerializer(data={
        "batchId": str(enr.batch.pk),
        "academicYearId": str(enr.academic_year.pk),
        "admissionNumber": "ADM-100",
        "firstName": "Alex",
        "parentName": "Bob",
    })
    assert prov_ser.is_valid(), prov_ser.errors
