"""Interactors — enrollment provisioning saga + transfer (F-081/F-082/F-085)."""

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.admissions.enums import ApplicationStatus, EnrollmentStatus
from apps.admissions.queries import application as app_q
from apps.admissions.queries import enrollment as enr_q
from apps.admissions.queries import provisioning as prov_q
from apps.fees.queries.structure import create_assignment, get_structure


class DuplicateStudentError(ValidationError):
    def __init__(self, matches):
        super().__init__({
            "code": "possible_duplicate",
            "message": "A student with the same name, date of birth, and phone already exists.",
            "matches": [str(m.pk) for m in matches],
        })


class LinkedAccountWarning(ValidationError):
    def __init__(self, existing_user):
        super().__init__({
            "code": "linked_account_warning",
            "message": "Phone/email matches an existing account. Confirm to create a linked account.",
            "existingUserId": str(existing_user.pk),
        })


def _check_quota(tenant):
    hard_cap = prov_q.student_hard_cap(tenant.pk)
    if hard_cap is None:
        return
    if prov_q.active_student_count(tenant.pk) >= hard_cap:
        raise ValidationError({"code": "limit_reached",
                               "message": "Student plan limit reached. Upgrade the plan to enroll more."})


class ProvisionEnrollmentInteractor:
    """Create student User + StudentProfile + StudentEnrollment, link parent, snapshot fee."""

    def __init__(self, *, branch, batch, academic_year, admission_number, first_name,
                 last_name="", date_of_birth=None, gender="", student_phone=None,
                 student_email=None, parent_name="", parent_phone=None, parent_email=None,
                 fee_structure_id=None, application=None, confirm_linked=False,
                 confirm_duplicate=False, sibling_group_id=None, tenant=None, user=None):
        self.branch = branch
        self.batch = batch
        self.academic_year = academic_year
        self.admission_number = admission_number
        self.first_name = first_name
        self.last_name = last_name
        self.date_of_birth = date_of_birth
        self.gender = gender
        self.student_phone = student_phone
        self.student_email = student_email
        self.parent_name = parent_name
        self.parent_phone = parent_phone
        self.parent_email = parent_email
        self.fee_structure_id = fee_structure_id
        self.application = application
        self.confirm_linked = confirm_linked
        self.confirm_duplicate = confirm_duplicate
        self.sibling_group_id = sibling_group_id
        self.tenant = tenant or branch.tenant
        self.user = user

    @transaction.atomic
    def execute(self):
        if self.application:
            if self.application.status == ApplicationStatus.ENROLLED:
                raise ValidationError({"application": "This application is already enrolled."})
            if self.application.status != ApplicationStatus.ACCEPTED:
                raise ValidationError({
                    "application": (
                        "Application must be accepted before enrollment. "
                        "Advance the pipeline to verification first."
                    ),
                })

        # 1. Admission-number uniqueness (EC-AUTH-24).
        if not self.admission_number:
            raise ValidationError({"admissionNumber": "Admission number / roll number is required."})
        if prov_q.custom_login_id_taken(self.tenant.pk, self.admission_number):
            raise ValidationError({"admissionNumber": "This Roll Number is already in use. Choose a different one."})

        # 2. Duplicate detection (F-080 / EC-DATA-03 / EC-GUARD-06).
        full_name = f"{self.first_name} {self.last_name}".strip()
        matches = prov_q.find_duplicate_students(
            self.branch.pk, name=full_name, date_of_birth=self.date_of_birth,
            phone=self.parent_phone or self.student_phone,
        )
        if matches and not self.confirm_duplicate:
            raise DuplicateStudentError(matches)

        # 3. Plan quota (EC-TEN-06).
        _check_quota(self.tenant)

        # 4. Student account + profile.
        student_user = prov_q.create_student_user(
            tenant=self.tenant, branch=self.branch, first_name=self.first_name,
            last_name=self.last_name, custom_login_id=self.admission_number,
            phone=self.student_phone, email=self.student_email, user=self.user,
        )
        profile = prov_q.create_student_profile(
            student_user=student_user, batch=self.batch, date_of_birth=self.date_of_birth,
            gender=self.gender, guardian_phone=self.parent_phone, user=self.user,
        )

        # 5. Parent linking (F-081 / EC-FORM-09): match existing same-tenant user.
        linked_existing = None
        if self.parent_phone or self.parent_email:
            existing = prov_q.find_user_by_phone_or_email(
                self.tenant.pk, phone=self.parent_phone, email=self.parent_email,
            )
            if existing and not self.confirm_linked:
                raise LinkedAccountWarning(existing)
            if existing:
                linked_existing = existing
                prov_q.link_user_group(existing, student_user)
                parent_user = existing
            else:
                pn = (self.parent_name or "Parent").split(" ", 1)
                parent_user = prov_q.create_parent_user(
                    tenant=self.tenant, branch=self.branch, first_name=pn[0],
                    last_name=pn[1] if len(pn) > 1 else "",
                    phone=self.parent_phone, email=self.parent_email,
                )
            prov_q.get_guardian_profile(parent_user)
            prov_q.create_guardian_link(
                student_user=student_user, guardian_user=parent_user,
                is_primary_contact=True, has_portal_access=True,
            )

        # 6. Enrollment record (the anchor).
        fee_structure = None
        if self.fee_structure_id:
            fee_structure = get_structure(self.branch.pk, self.fee_structure_id)
        enrollment = enr_q.create_enrollment(
            branch=self.branch, student_profile=profile, batch=self.batch,
            academic_year=self.academic_year, application=self.application,
            fee_structure_snapshot=fee_structure, sibling_group_id=self.sibling_group_id,
            user=self.user,
        )
        # keep StudentProfile.current_batch in sync (it already is, set at creation).

        # 7. Fee snapshot at enrollment (F-082 / F-150).
        if fee_structure:
            create_assignment(
                student=enrollment, fee_structure=fee_structure,
                structure_snapshot=fee_structure.components or [], discount_lines=[],
                user=self.user,
            )

        # 8. Mark application enrolled.
        if self.application:
            app_q.update_application(self.application, {"status": ApplicationStatus.ENROLLED}, user=self.user)

        return {
            "status": "completed",
            "studentUserId": str(student_user.pk),
            "studentProfileId": str(profile.pk),
            "enrollmentId": str(enrollment.pk),
            "linkedExistingParent": str(linked_existing.pk) if linked_existing else None,
            "feeSnapshotApplied": bool(fee_structure),
        }


@transaction.atomic
def transfer_enrollment(*, enrollment, to_branch, to_batch, academic_year, user=None):
    """F-085 / EC-XFER-01 — archive the source enrollment, create one at the new branch."""
    if not enrollment or not enrollment.is_active:
        raise ValidationError({"enrollment": "Source enrollment not found."})

    enr_q.update_enrollment(enrollment, {
        "status": EnrollmentStatus.TRANSFERRED, "is_active": False,
    }, user=user)

    new_enrollment = enr_q.create_enrollment(
        branch=to_branch, student_profile=enrollment.student_profile, batch=to_batch,
        academic_year=academic_year, is_transferred=True,
        transferred_from_branch=enrollment.branch,
        backlog_subjects=enrollment.backlog_subjects, user=user,
    )
    return new_enrollment
