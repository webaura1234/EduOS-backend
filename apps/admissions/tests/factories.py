import factory
from factory.django import DjangoModelFactory

from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.academics.tests.factories import BatchFactory, AcademicYearFactory, CourseFactory
from apps.admissions.enums import ApplicationStatus, DocVerificationStatus, EnquirySource, EnquiryStatus, EnrollmentStatus
from apps.admissions.models.application import Application, ApplicationDocument, Enquiry, Waitlist
from apps.admissions.models.enrollment import StudentEnrollment
from apps.organizations.tests.factories import BranchFactory


class EnquiryFactory(DjangoModelFactory):
    class Meta:
        model = Enquiry

    branch = factory.SubFactory(BranchFactory)
    source = EnquirySource.WALK_IN
    course = factory.SubFactory(CourseFactory, department__branch=factory.SelfAttribute("...branch"))
    applicant_name = factory.Sequence(lambda n: f"Applicant {n}")
    phone = "+919876543210"
    email = factory.Sequence(lambda n: f"app-{n}@example.com")
    status = EnquiryStatus.NEW


class ApplicationFactory(DjangoModelFactory):
    class Meta:
        model = Application

    branch = factory.SubFactory(BranchFactory)
    enquiry = factory.SubFactory(EnquiryFactory, branch=factory.SelfAttribute("..branch"))
    course = factory.LazyAttribute(lambda o: o.enquiry.course)
    status = ApplicationStatus.DRAFT
    step = factory.LazyFunction(dict)
    eligibility_result = factory.LazyFunction(dict)


class ApplicationDocumentFactory(DjangoModelFactory):
    class Meta:
        model = ApplicationDocument

    application = factory.SubFactory(ApplicationFactory)
    doc_type = "Aadhar Card"
    s3_key = factory.Sequence(lambda n: f"docs/aadhar-{n}.pdf")
    verification_status = DocVerificationStatus.PENDING


class WaitlistFactory(DjangoModelFactory):
    class Meta:
        model = Waitlist

    branch = factory.SubFactory(BranchFactory)
    application = factory.SubFactory(
        ApplicationFactory,
        branch=factory.SelfAttribute("..branch"),
        status=ApplicationStatus.WAITLISTED,
    )
    course = factory.LazyAttribute(lambda o: o.application.course)
    rank = factory.Sequence(lambda n: n + 1)


class StudentEnrollmentFactory(DjangoModelFactory):
    class Meta:
        model = StudentEnrollment

    # We will resolve all fields in _create to avoid subfactory nested attributes bugs
    branch = None
    batch = None
    academic_year = None
    student_profile = None
    status = EnrollmentStatus.ACTIVE
    
    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        branch = kwargs.get("branch")
        batch = kwargs.get("batch")
        academic_year = kwargs.get("academic_year")
        student_profile = kwargs.get("student_profile")
        
        # 1. Resolve branch
        if branch is None:
            if batch is not None:
                branch = batch.course.department.branch
            elif student_profile is not None:
                branch = student_profile.user.branch
            else:
                branch = BranchFactory()
        kwargs["branch"] = branch
        
        # 2. Resolve batch
        if batch is None:
            batch = BatchFactory(course__department__branch=branch)
        kwargs["batch"] = batch
        
        # 3. Resolve academic year
        if academic_year is None:
            academic_year = batch.academic_year
        kwargs["academic_year"] = academic_year
        
        # 4. Resolve student profile
        if student_profile is None:
            user = UserFactory(role=Role.STUDENT, branch=branch, tenant=branch.tenant)
            student_profile = StudentProfile.objects.create(
                user=user,
                current_batch=batch,
                academic_status="active",
            )
        kwargs["student_profile"] = student_profile
        
        return super()._create(model_class, *args, **kwargs)
