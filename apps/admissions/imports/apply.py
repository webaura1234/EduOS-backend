"""Apply a validated import row (create / update)."""

from __future__ import annotations

from datetime import date

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role, User
from apps.academics.queries.structure import get_batch
from apps.admissions.interactors.enrollment import (
    DuplicateStudentError,
    LinkedAccountWarning,
    ProvisionEnrollmentInteractor,
)
from apps.admissions.queries import enrollment as enr_q
from apps.admissions.queries import provisioning as prov_q
from apps.fees.queries.structure import create_assignment, get_structure


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@transaction.atomic
def create_student_from_row(*, branch, academic_year, data: dict, user=None) -> dict:
    batch_id = data.get("batchId")
    batch = get_batch(branch.pk, batch_id) if batch_id else None
    if not batch:
        raise ValidationError({"class": "Valid class/section is required to create a student."})

    fee_id = data.get("feeStructureId") or None
    try:
        result = ProvisionEnrollmentInteractor(
            branch=branch,
            batch=batch,
            academic_year=academic_year,
            admission_number=(data.get("admission_number") or "").strip(),
            first_name=(data.get("first_name") or "").strip(),
            last_name=(data.get("last_name") or "").strip(),
            date_of_birth=_parse_date(data.get("date_of_birth")),
            gender=(data.get("gender") or "").strip(),
            student_phone=(data.get("student_mobile") or None) or None,
            student_email=(data.get("student_email") or None) or None,
            parent_name=(data.get("parent_name") or "").strip(),
            parent_phone=(data.get("parent_mobile") or None) or None,
            parent_email=(data.get("parent_email") or None) or None,
            fee_structure_id=fee_id,
            confirm_linked=True,
            confirm_duplicate=True,
            tenant=branch.tenant,
            user=user,
        ).execute()
    except (DuplicateStudentError, LinkedAccountWarning) as exc:
        # Should be rare with confirm flags; surface cleanly.
        raise ValidationError(exc.detail) from exc
    return result


@transaction.atomic
def update_student_from_row(*, branch, academic_year, data: dict, user=None) -> dict:
    """Patch an existing student matched by admission number (custom_login_id)."""
    adm = (data.get("admission_number") or "").strip()
    student_user = (
        User.objects.filter(
            tenant_id=branch.tenant_id,
            role=Role.STUDENT,
            custom_login_id__iexact=adm,
            is_active=True,
        )
        .select_related("student_profile")
        .first()
    )
    if not student_user:
        raise ValidationError({"admissionNumber": "Student not found."})

    first = (data.get("first_name") or "").strip()
    last = (data.get("last_name") or "").strip()
    if first:
        student_user.first_name = first
    if last or first:
        if last:
            student_user.last_name = last
        elif first:
            # Keep existing last name unless explicitly cleared via last_name key present empty — leave as-is
            pass
    if data.get("student_mobile"):
        student_user.phone = data["student_mobile"]
    if data.get("student_email"):
        student_user.email = data["student_email"]
    student_user.save()

    profile = getattr(student_user, "student_profile", None)
    if profile is None:
        profile = StudentProfile.objects.filter(user=student_user).first()
    if profile is None:
        raise ValidationError({"admissionNumber": "Student profile missing."})

    updates = {}
    dob = _parse_date(data.get("date_of_birth"))
    if dob:
        updates["date_of_birth"] = dob
    if data.get("gender"):
        updates["gender"] = data["gender"]
    if data.get("parent_mobile"):
        updates["guardian_phone"] = data["parent_mobile"]

    batch_id = data.get("batchId")
    batch = get_batch(branch.pk, batch_id) if batch_id else None
    if batch:
        updates["current_batch"] = batch

    if updates:
        for k, v in updates.items():
            setattr(profile, k, v)
        if user:
            profile.updated_by = user
        profile.save()

    enrollment = enr_q.resolve_enrollment_for_profile(
        profile, academic_year=academic_year, batch=batch or profile.current_batch, create=False
    )
    if enrollment is None and batch:
        enrollment = enr_q.create_enrollment(
            branch=branch,
            student_profile=profile,
            batch=batch,
            academic_year=academic_year,
            user=user,
        )
    elif enrollment and batch and enrollment.batch_id != batch.pk:
        enr_q.update_enrollment(enrollment, {"batch": batch}, user=user)

    fee_id = data.get("feeStructureId")
    if fee_id and enrollment:
        fee = get_structure(branch.pk, fee_id)
        if fee:
            from apps.fees.services.concession_sync import rebuild_assignment_discounts

            enr_q.update_enrollment(enrollment, {"fee_structure_snapshot": fee}, user=user)
            # Avoid duplicate assignments: only create if none for this enrollment+structure.
            from apps.fees.models.structure import StudentFeeAssignment

            existing = StudentFeeAssignment.objects.filter(
                student=enrollment, fee_structure=fee, is_active=True
            ).first()
            if not existing:
                assignment = create_assignment(
                    student=enrollment,
                    fee_structure=fee,
                    structure_snapshot=fee.components or [],
                    discount_lines=[],
                    user=user,
                )
                rebuild_assignment_discounts(assignment, user=user)

    # Parent contact: ensure guardian link if parent phone provided.
    parent_phone = (data.get("parent_mobile") or "").strip() or None
    parent_email = (data.get("parent_email") or "").strip() or None
    parent_name = (data.get("parent_name") or "").strip()
    if parent_phone or parent_email:
        parent_user = prov_q.find_user_by_phone_or_email(
            branch.tenant_id, phone=parent_phone, email=parent_email, role=Role.PARENT
        )
        if not parent_user and parent_name:
            pn = parent_name.split(" ", 1)
            parent_user = prov_q.create_parent_user(
                tenant=branch.tenant,
                branch=branch,
                first_name=pn[0],
                last_name=pn[1] if len(pn) > 1 else "",
                phone=parent_phone,
                email=parent_email,
            )
        if parent_user:
            prov_q.get_guardian_profile(parent_user)
            from apps.accounts.models.guardian import StudentGuardianLink

            link_exists = StudentGuardianLink.objects.filter(
                student=student_user, guardian=parent_user, is_active=True
            ).exists()
            if not link_exists:
                prov_q.create_guardian_link(
                    student_user=student_user,
                    guardian_user=parent_user,
                    is_primary_contact=True,
                    has_portal_access=True,
                )

    return {
        "status": "updated",
        "studentUserId": str(student_user.pk),
        "studentProfileId": str(profile.pk),
        "enrollmentId": str(enrollment.pk) if enrollment else None,
    }


def apply_row(*, action: str, branch, academic_year, data: dict, user=None) -> dict:
    if action == "create":
        return create_student_from_row(
            branch=branch, academic_year=academic_year, data=data, user=user
        )
    if action == "update":
        return update_student_from_row(
            branch=branch, academic_year=academic_year, data=data, user=user
        )
    raise ValidationError({"action": f"Unknown action '{action}'."})
