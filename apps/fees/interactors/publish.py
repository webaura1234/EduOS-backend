"""Fee structure publish, archive, and version interactors."""

import datetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.fees.enums import FeeStructureStatus, InvoiceStatus
from apps.fees.interactors.fee_structure import validate_components
from apps.fees.models import FeeInvoice, FeeStructure, StudentFeeAssignment
from apps.fees.queries.structure import create_structure, update_structure


def structure_invoice_count(structure_id) -> int:
    return FeeInvoice.objects.filter(
        assignment__fee_structure_id=structure_id,
        is_active=True,
    ).count()


def structure_assignment_count(structure_id) -> int:
    return StudentFeeAssignment.objects.filter(
        fee_structure_id=structure_id,
        is_active=True,
    ).count()


def structure_is_locked(structure: FeeStructure) -> bool:
    if structure.status != FeeStructureStatus.PUBLISHED:
        return False
    return structure_invoice_count(structure.id) > 0


def structure_impact(structure: FeeStructure) -> dict:
    invoice_count = structure_invoice_count(structure.id)
    assignment_count = structure_assignment_count(structure.id)
    unpaid = FeeInvoice.objects.filter(
        assignment__fee_structure_id=structure.id,
        is_active=True,
        status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL],
    ).count()
    return {
        "version": structure.version,
        "invoiceCount": invoice_count,
        "assignmentCount": assignment_count,
        "isLocked": structure.status == FeeStructureStatus.PUBLISHED and invoice_count > 0,
        "unpaidInvoiceCount": unpaid,
    }


@transaction.atomic
def publish_fee_structure(*, structure: FeeStructure, user=None) -> FeeStructure:
    if structure.status == FeeStructureStatus.ARCHIVED:
        raise ValidationError("Cannot publish an archived structure.")
    validate_components(structure.components or [])
    if not (structure.components or []):
        raise ValidationError("Fee structure must have at least one component.")
    if not structure.batch_id:
        raise ValidationError("Fee structure must be assigned to a class/section before publishing.")

    structure.status = FeeStructureStatus.PUBLISHED
    structure.published_at = timezone.now()
    structure.published_by = user
    if user:
        structure.updated_by = user
    structure.save(update_fields=["status", "published_at", "published_by", "updated_by", "updated_at"])
    return structure


@transaction.atomic
def archive_fee_structure(*, structure: FeeStructure, user=None, force: bool = False) -> FeeStructure:
    impact = structure_impact(structure)
    if not force:
        if impact["unpaidInvoiceCount"] > 0:
            raise ValidationError(
                f"{impact['unpaidInvoiceCount']} invoice(s) still have outstanding balance."
            )
        if impact["assignmentCount"] > 0:
            raise ValidationError(
                f"{impact['assignmentCount']} student(s) are actively assigned to this structure."
            )
        if structure.academic_year_id and getattr(structure.academic_year, "is_current", False):
            raise ValidationError("Cannot archive while the academic year is still active.")

    structure.status = FeeStructureStatus.ARCHIVED
    structure.is_active = False
    if user:
        structure.updated_by = user
    structure.save(update_fields=["status", "is_active", "updated_by", "updated_at"])
    return structure


@transaction.atomic
def create_new_structure_version(
    *,
    structure: FeeStructure,
    user=None,
) -> FeeStructure:
    if structure.status != FeeStructureStatus.PUBLISHED:
        raise ValidationError("New version can only be created from a published structure.")
    if not structure_is_locked(structure):
        raise ValidationError("Structure is not locked; edit the draft or published structure directly.")

    return create_structure(
        branch_id=structure.branch_id,
        name=structure.name,
        academic_year_id=structure.academic_year_id,
        batch_id=structure.batch_id,
        components=list(structure.components or []),
        user=user,
        status=FeeStructureStatus.DRAFT,
        parent_structure_id=structure.id,
        version=structure.version + 1,
    )


@transaction.atomic
def update_fee_structure_guarded(
    *,
    structure: FeeStructure,
    name=None,
    components=None,
    user=None,
) -> FeeStructure:
    if structure_is_locked(structure):
        raise ValidationError(
            "This fee structure is locked because invoices have been generated. "
            "Create a new version instead."
        )
    fields = {}
    if name is not None:
        if not name.strip():
            raise ValidationError("Structure name cannot be blank.")
        fields["name"] = name
    if components is not None:
        validate_components(components)
        fields["components"] = components
    if not fields:
        return structure
    return update_structure(structure, fields, user=user)
