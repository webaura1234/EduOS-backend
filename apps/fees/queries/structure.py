"""Queries — FeeStructure, StudentFeeAssignment, and student lookup."""

from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.fees.models import FeeStructure, StudentFeeAssignment


def get_student_in_branch(branch_id, student_id) -> StudentProfile | None:
    try:
        return StudentProfile.objects.select_related("user", "current_batch").get(
            pk=student_id, current_batch__course__department__branch_id=branch_id, is_active=True
        )
    except (StudentProfile.DoesNotExist, ValueError, TypeError):
        return None


def students_in_batch(batch_id):
    return StudentProfile.objects.filter(
        current_batch_id=batch_id, academic_status=AcademicStatus.ACTIVE, is_active=True
    ).select_related("user")


def get_student_profile(student_id) -> StudentProfile | None:
    try:
        return StudentProfile.objects.select_related("user").get(pk=student_id, is_active=True)
    except (StudentProfile.DoesNotExist, ValueError, TypeError):
        return None


def get_assignment_by_id(assignment_id):
    from apps.fees.models import StudentFeeAssignment
    try:
        return StudentFeeAssignment.objects.select_related("student", "fee_structure").get(
            pk=assignment_id, is_active=True
        )
    except (StudentFeeAssignment.DoesNotExist, ValueError, TypeError):
        return None


def list_assignments_for_student(student_id):
    from apps.fees.models import StudentFeeAssignment
    return StudentFeeAssignment.objects.filter(student_id=student_id, is_active=True)


def get_assignment_for_student_structure(student_id, structure_id):
    from apps.fees.models import StudentFeeAssignment
    try:
        return StudentFeeAssignment.objects.get(
            student_id=student_id, fee_structure_id=structure_id, is_active=True
        )
    except (StudentFeeAssignment.DoesNotExist, ValueError, TypeError):
        return None


def update_assignment(assignment, fields: dict, user=None):
    for k, v in fields.items():
        setattr(assignment, k, v)
    if user:
        assignment.updated_by = user
    assignment.save(update_fields=list(fields.keys()) + (["updated_by"] if user else []) + ["updated_at"])
    return assignment


def billing_guardian_for_student(student):
    """The GuardianProfile of the student's primary portal guardian, or None."""
    link = student.user.guardian_links.filter(has_portal_access=True, is_active=True).first()
    if not link:
        return None
    try:
        return link.guardian.guardian_profile
    except AttributeError:
        return None


# ── FeeStructure ──────────────────────────────────────────────────────────────
def list_structures(branch_id, academic_year_id=None):
    qs = FeeStructure.objects.filter(branch_id=branch_id, is_active=True).select_related("batch", "academic_year")
    if academic_year_id:
        qs = qs.filter(academic_year_id=academic_year_id)
    return qs.order_by("name")


def get_structure(branch_id, structure_id) -> FeeStructure | None:
    try:
        return FeeStructure.objects.get(branch_id=branch_id, pk=structure_id, is_active=True)
    except (FeeStructure.DoesNotExist, ValueError, TypeError):
        return None


def create_structure(*, branch_id, name, academic_year_id, batch_id=None, components, user=None) -> FeeStructure:
    return FeeStructure.objects.create(
        branch_id=branch_id, name=name, academic_year_id=academic_year_id, batch_id=batch_id,
        components=components, created_by=user, updated_by=user,
    )


def update_structure(structure: FeeStructure, fields: dict, user=None) -> FeeStructure:
    for k, v in fields.items():
        setattr(structure, k, v)
    structure.version += 1
    if user:
        structure.updated_by = user
    structure.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return structure


# ── StudentFeeAssignment ──────────────────────────────────────────────────────
def get_assignment(branch_id, assignment_id) -> StudentFeeAssignment | None:
    try:
        return StudentFeeAssignment.objects.select_related("student", "fee_structure").get(
            pk=assignment_id, fee_structure__branch_id=branch_id, is_active=True
        )
    except (StudentFeeAssignment.DoesNotExist, ValueError, TypeError):
        return None


def assignment_exists(student_id, structure_id) -> bool:
    return StudentFeeAssignment.objects.filter(
        student_id=student_id, fee_structure_id=structure_id, is_active=True
    ).exists()


def create_assignment(*, student, fee_structure, structure_snapshot, discount_lines, user=None) -> StudentFeeAssignment:
    return StudentFeeAssignment.objects.create(
        student=student, fee_structure=fee_structure, structure_snapshot=structure_snapshot,
        discount_lines=discount_lines, created_by=user, updated_by=user,
    )
