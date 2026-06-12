import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError

from apps.accounts.models.user import User, Role
from apps.accounts.models.profile import StudentProfile
from apps.admissions.enums import ApplicationStatus, DocVerificationStatus, EnquiryStatus, EnrollmentStatus
from apps.admissions.interactors import (
    capture_enquiry,
    convert_enquiry_to_application,
    save_application_step,
    add_application_document,
    verify_document,
    reject_application,
    detect_duplicates,
    resolve_sibling_group_id,
    get_merit_list,
    add_to_waitlist,
    promote_waitlist_entry,
    ProvisionEnrollmentInteractor,
    transfer_enrollment,
)
from apps.admissions.models.application import ApplicationDocument, Enquiry
from apps.admissions.models.enrollment import StudentEnrollment
from apps.admissions.tests.factories import (
    EnquiryFactory,
    ApplicationFactory,
    ApplicationDocumentFactory,
    WaitlistFactory,
    StudentEnrollmentFactory,
)
from apps.academics.tests.factories import BatchFactory, AcademicYearFactory, CourseFactory, DepartmentFactory
from apps.organizations.tests.factories import BranchFactory, TenantFactory
from apps.fees.models import FeeStructure

pytestmark = pytest.mark.django_db


def test_capture_enquiry_interactor():
    branch = BranchFactory()
    course = CourseFactory(department__branch=branch)
    
    enquiry = capture_enquiry(
        branch=branch,
        source="walk_in",
        applicant_name="Test Applicant",
        course=course,
        phone="+919999999999",
        email="test@example.com",
        notes="Important notes",
    )
    
    assert enquiry.pk is not None
    assert enquiry.applicant_name == "Test Applicant"
    assert enquiry.status == EnquiryStatus.NEW


def test_convert_enquiry_to_application_interactor():
    enquiry = EnquiryFactory()
    
    app = convert_enquiry_to_application(enquiry=enquiry)
    
    assert app.pk is not None
    assert app.status == ApplicationStatus.SUBMITTED
    
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.CONVERTED


def test_save_application_step_interactor():
    app = ApplicationFactory()
    
    save_application_step(
        branch_id=app.branch.pk,
        application_id=app.pk,
        step={"step": 2, "percentage": 50},
    )
    
    app.refresh_from_db()
    assert app.step == {"step": 2, "percentage": 50}


def test_document_and_verification_interactors():
    app = ApplicationFactory()
    
    doc = add_application_document(
        branch_id=app.branch.pk,
        application_id=app.pk,
        doc_type="ID Card",
        s3_key="s3://bucket/id.png",
    )
    assert doc.pk is not None
    assert doc.doc_type == "ID Card"
    assert doc.verification_status == DocVerificationStatus.PENDING
    
    # verify
    verify_document(
        branch_id=app.branch.pk,
        document_id=doc.pk,
        verification_status=DocVerificationStatus.VERIFIED,
    )
    doc.refresh_from_db()
    assert doc.verification_status == DocVerificationStatus.VERIFIED


def test_reject_application_interactor():
    app = ApplicationFactory()
    
    reject_application(
        branch_id=app.branch.pk,
        application_id=app.pk,
        rejection_reason="Incomplete documentation",
    )
    app.refresh_from_db()
    assert app.status == ApplicationStatus.REJECTED
    assert app.rejection_reason == "Incomplete documentation"


def test_duplicate_detection_and_sibling_resolver():
    branch = BranchFactory()
    student_enr = StudentEnrollmentFactory(branch=branch)
    student_profile = student_enr.student_profile
    student_user = student_profile.user
    
    # detect duplicate
    matches = detect_duplicates(
        branch_id=branch.pk,
        first_name=student_user.first_name,
        last_name=student_user.last_name,
        date_of_birth=student_profile.date_of_birth,
        phone=student_user.phone,
    )
    assert student_profile in matches
    
    # sibling override
    group_id = resolve_sibling_group_id(
        branch_id=branch.pk,
        sibling_student_profile_id=student_profile.pk,
    )
    assert group_id is not None
    
    student_enr.refresh_from_db()
    assert student_enr.sibling_group_id == group_id


def test_merit_list_and_waitlist_interactors():
    branch = BranchFactory()
    course = CourseFactory(department__branch=branch)
    enq1 = EnquiryFactory(branch=branch, course=course)
    app1 = convert_enquiry_to_application(enquiry=enq1)
    
    # Add eligibility score
    app1.eligibility_result = {"score": 85.5}
    app1.save()
    
    enq2 = EnquiryFactory(branch=branch, course=course)
    app2 = convert_enquiry_to_application(enquiry=enq2)
    app2.eligibility_result = {"score": 92.0}
    app2.save()
    
    # get merit list (descending score)
    merit = get_merit_list(branch_id=branch.pk, course_id=course.pk)
    assert merit[0] == app2
    assert merit[1] == app1
    
    # add to waitlist
    wl1 = add_to_waitlist(branch=branch, application=app1, rank=1)
    assert wl1.pk is not None
    assert wl1.rank == 1
    
    wl2 = add_to_waitlist(branch=branch, application=app2, rank=2)
    assert wl2.rank == 2
    
    # promote wl1
    promote_waitlist_entry(branch_id=branch.pk, waitlist_entry_id=wl1.pk)
    app1.refresh_from_db()
    assert app1.status == ApplicationStatus.ACCEPTED
    
    # wl2 should have rank shifted to 1
    wl2.refresh_from_db()
    assert wl2.rank == 1


def test_provision_enrollment_interactor():
    tenant = TenantFactory()
    branch = BranchFactory(tenant=tenant)
    batch = BatchFactory(course__department__branch=branch)
    academic_year = batch.academic_year
    
    fee_struct = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        name="Tuition Only",
        components=[]
    )
    
    interactor = ProvisionEnrollmentInteractor(
        branch=branch,
        batch=batch,
        academic_year=academic_year,
        admission_number="ADM-9999",
        first_name="John",
        last_name="Doe",
        parent_name="Jane Doe",
        parent_phone="+919876543210",
        fee_structure_id=fee_struct.pk,
    )
    
    res = interactor.execute()
    assert res["status"] == "completed"
    
    # assert DB objects
    assert User.objects.filter(custom_login_id="ADM-9999", role=Role.STUDENT).exists()
    assert StudentEnrollment.objects.filter(pk=res["enrollmentId"]).exists()


def test_transfer_enrollment_interactor():
    enr = StudentEnrollmentFactory()
    
    to_branch = BranchFactory(tenant=enr.branch.tenant)
    to_batch = BatchFactory(course__department__branch=to_branch)
    
    new_enr = transfer_enrollment(
        enrollment=enr,
        to_branch=to_branch,
        to_batch=to_batch,
        academic_year=to_batch.academic_year,
    )
    
    assert new_enr.pk is not None
    assert new_enr.branch == to_branch
    assert new_enr.batch == to_batch
    
    enr.refresh_from_db()
    assert enr.status == EnrollmentStatus.TRANSFERRED
    assert enr.is_active is False
