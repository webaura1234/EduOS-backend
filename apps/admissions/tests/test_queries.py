import pytest
from apps.admissions.enums import EnquiryStatus, ApplicationStatus
from apps.admissions.queries import enquiry as enquiry_q
from apps.admissions.queries import application as app_q
from apps.admissions.queries import enrollment as enr_q
from apps.admissions.tests.factories import EnquiryFactory, ApplicationFactory, WaitlistFactory, StudentEnrollmentFactory

pytestmark = pytest.mark.django_db


def test_enquiry_queries():
    enquiry = EnquiryFactory()
    
    # get
    fetched = enquiry_q.get_enquiry(enquiry.branch.pk, enquiry.pk)
    assert fetched == enquiry
    
    # list
    enquiries = enquiry_q.list_enquiries(enquiry.branch.pk)
    assert enquiry in enquiries
    
    # create
    new_enq = enquiry_q.create_enquiry(
        branch=enquiry.branch,
        source="online",
        applicant_name="New Enq",
    )
    assert new_enq.pk is not None
    
    # update
    updated = enquiry_q.update_enquiry(enquiry, {"status": EnquiryStatus.CONTACTED})
    assert updated.status == EnquiryStatus.CONTACTED
    
    # funnel counts
    counts = enquiry_q.funnel_counts(enquiry.branch.pk)
    assert "bySource" in counts
    assert "byStatus" in counts


def test_application_queries():
    app = ApplicationFactory()
    
    # get
    fetched = app_q.get_application(app.branch.pk, app.pk)
    assert fetched == app
    
    # list
    apps = app_q.list_applications(app.branch.pk)
    assert app in apps
    
    # create
    new_app = app_q.create_application(
        branch=app.branch,
        enquiry=EnquiryFactory(branch=app.branch),
    )
    assert new_app.pk is not None
    
    # update
    updated = app_q.update_application(app, {"status": ApplicationStatus.UNDER_REVIEW})
    assert updated.status == ApplicationStatus.UNDER_REVIEW


def test_waitlist_queries():
    wl = WaitlistFactory()
    
    # ranked
    ranked = app_q.ranked_applications_for_course(wl.branch.pk, wl.course.pk)
    assert wl.application in ranked
    
    # get
    fetched = app_q.get_waitlist_entry(wl.branch.pk, wl.pk)
    assert fetched == wl
    
    # list
    entries = app_q.list_waitlist(wl.branch.pk, course_id=wl.course.pk)
    assert wl in entries


def test_enrollment_queries():
    enr = StudentEnrollmentFactory()
    
    # get
    fetched = enr_q.get_enrollment_by_id(enr.pk)
    assert fetched == enr
    
    # active profile enrollment
    active = enr_q.get_active_enrollment_for_profile(enr.student_profile.pk)
    assert active == enr
    
    # list
    enrollments = enr_q.list_enrollments(enr.branch.pk)
    assert enr in enrollments
    
    # roster
    roster = enr_q.enrollments_in_batch(enr.batch.pk)
    assert enr in roster
