import pytest
from apps.admissions.enums import EnquiryStatus, ApplicationStatus, EnrollmentStatus
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


def test_enrollment_include_inactive_reaches_prior_year_enrollment():
    """After rollover the prior-year enrollment is soft-deactivated (is_active=False).
    It must stay hidden by default but be reachable via include_inactive=True — the
    historical read path (audit P1.1)."""
    enr = StudentEnrollmentFactory()
    profile_id = enr.student_profile_id
    year_id = enr.academic_year_id
    branch_id = enr.branch_id

    # Simulate the rollover deactivation of the source-year enrollment.
    enr.is_active = False
    enr.save(update_fields=["is_active"])

    # Default (current-only) semantics unchanged — prior-year enrollment is hidden.
    assert enr_q.get_active_enrollment_for_profile(profile_id, academic_year_id=year_id) is None
    assert enr_q.get_enrollment_by_id(enr.pk) is None
    assert enr not in list(enr_q.list_enrollments(branch_id))

    # Historical read path — reachable only when explicitly opted in.
    assert (
        enr_q.get_active_enrollment_for_profile(
            profile_id, academic_year_id=year_id, include_inactive=True
        )
        == enr
    )
    assert enr_q.get_enrollment_by_id(enr.pk, include_inactive=True) == enr
    assert enr in list(enr_q.list_enrollments(branch_id, include_inactive=True))


def test_enrollment_for_profile_in_branch_active_vs_inactive():
    enr = StudentEnrollmentFactory()
    profile_id = enr.student_profile_id
    branch_id = enr.branch_id

    assert enr_q.get_enrollment_for_profile_in_branch(profile_id, branch_id) == enr
    assert enr_q.get_enrollment_for_profile_in_branch(profile_id, branch_id, include_inactive=False) == enr

    enr.is_active = False
    enr.status = EnrollmentStatus.GRADUATED
    enr.save(update_fields=["is_active", "status"])

    assert enr_q.get_enrollment_for_profile_in_branch(profile_id, branch_id) is None
    assert (
        enr_q.get_enrollment_for_profile_in_branch(profile_id, branch_id, include_inactive=True)
        == enr
    )


def test_resolve_enrollment_for_profile_falls_back_to_terminal_enrollment():
    enr = StudentEnrollmentFactory()
    profile = enr.student_profile
    profile.current_batch = None
    profile.current_enrollment = enr
    profile.save(update_fields=["current_batch", "current_enrollment"])

    enr.is_active = False
    enr.status = EnrollmentStatus.GRADUATED
    enr.save(update_fields=["is_active", "status"])

    resolved = enr_q.resolve_enrollment_for_profile(profile, create=False)
    assert resolved == enr
