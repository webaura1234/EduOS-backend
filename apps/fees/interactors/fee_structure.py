"""Fee structure interactors."""

import datetime
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.fees.enums import FeeComponentKind
from apps.fees.models import FeeStructure
from apps.fees.queries.structure import create_structure, update_structure


def validate_components(components):
    """Validates the structure of the JSON components list."""
    if not isinstance(components, list):
        raise ValidationError("Components must be a list.")
    
    valid_kinds = set(FeeComponentKind.values)
    for c in components:
        if not isinstance(c, dict):
            raise ValidationError("Each component must be a dictionary.")
        
        kind = c.get("kind")
        if kind not in valid_kinds:
            raise ValidationError(f"Invalid component kind: '{kind}'. Must be one of {list(valid_kinds)}.")
        
        if "label" not in c or not isinstance(c["label"], str) or not c["label"].strip():
            raise ValidationError("Component label is required and must be a string.")
        
        amount = c.get("amount_paise")
        if amount is None or not isinstance(amount, int) or amount < 0:
            raise ValidationError("Component amount_paise must be a non-negative integer.")
        
        due_date = c.get("due_date")
        if not due_date:
            raise ValidationError("Component due_date is required.")
        try:
            datetime.date.fromisoformat(due_date)
        except ValueError:
            raise ValidationError("Component due_date must be in YYYY-MM-DD format.")
            
        inst_no = c.get("installment_no")
        if inst_no is None or not isinstance(inst_no, int) or inst_no < 1:
            raise ValidationError("Component installment_no must be a positive integer starting from 1.")


@transaction.atomic
def create_fee_structure(*, branch_id, name, academic_year_id, batch_id=None, components, user=None) -> FeeStructure:
    """Creates a new FeeStructure after validating the name and components."""
    if not name or not name.strip():
        raise ValidationError("Structure name is required.")
    
    validate_components(components)
    
    return create_structure(
        branch_id=branch_id,
        name=name,
        academic_year_id=academic_year_id,
        batch_id=batch_id,
        components=components,
        user=user,
    )


@transaction.atomic
def update_fee_structure(*, structure: FeeStructure, name=None, components=None, user=None) -> FeeStructure:
    """Updates an existing FeeStructure, bumping its version."""
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
