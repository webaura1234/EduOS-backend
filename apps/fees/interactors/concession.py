"""Concession interactors."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.fees.enums import ConcessionStatus
from apps.fees.models import ConcessionRequest, ConcessionRule
from apps.fees.queries.concession import (
    create_concession_request,
    create_concession_rule,
    get_concession_request_for_update,
    get_concession_rule,
    update_concession_request,
)
from apps.fees.helpers.concession import concession_amount_paise
from apps.fees.queries.structure import list_assignments_for_student, update_assignment


class CreateConcessionRuleInteractor:
    """Creates a new concession rule."""

    def __init__(self, branch, name, amount_paise=None, percent=None, criteria=None, user=None):
        self.branch = branch
        self.name = name
        self.amount_paise = amount_paise
        self.percent = percent
        self.criteria = criteria
        self.user = user

    def execute(self) -> ConcessionRule:
        if not self.name or not self.name.strip():
            raise ValidationError("Rule name is required.")
        if self.amount_paise is None and self.percent is None:
            raise ValidationError("Either amount_paise or percent must be provided.")
        if self.amount_paise is not None and self.percent is not None:
            raise ValidationError("Cannot provide both amount_paise and percent.")
        if self.percent is not None and (self.percent < 0 or self.percent > 100):
            raise ValidationError("Percentage discount must be between 0 and 100.")
        if self.amount_paise is not None and self.amount_paise <= 0:
            raise ValidationError("Discount amount must be greater than zero.")

        return create_concession_rule(
            branch=self.branch, name=self.name, amount_paise=self.amount_paise,
            percent=self.percent, criteria=self.criteria, user=self.user,
        )


class CreateConcessionRequestInteractor:
    """Creates a concession request for a student."""

    def __init__(self, branch, student, rule_id, amount_paise, requested_by, note=""):
        self.branch = branch
        self.student = student
        self.rule_id = rule_id
        self.amount_paise = amount_paise
        self.requested_by = requested_by
        self.note = note

    def execute(self) -> ConcessionRequest:
        rule = None
        if self.rule_id:
            rule = get_concession_rule(self.branch.id, self.rule_id)
            if rule is None:
                raise ValidationError("Concession rule not found.")
        if self.amount_paise <= 0:
            if rule and rule.percent:
                self.amount_paise = 1  # placeholder; resolved at approval from structure totals
            else:
                raise ValidationError("Concession amount must be greater than zero.")

        return create_concession_request(
            branch=self.branch, student=self.student, rule=rule, amount_paise=self.amount_paise,
            requested_by=self.requested_by, note=self.note, user=self.requested_by,
        )


class ApproveConcessionRequestInteractor:
    """Approves/rejects a concession request; on approval appends it to discount_lines."""

    def __init__(self, request_id, status, approver_user):
        self.request_id = request_id
        self.status = status
        self.approver_user = approver_user

    @transaction.atomic
    def execute(self) -> ConcessionRequest:
        if self.status not in [ConcessionStatus.APPROVED, ConcessionStatus.REJECTED]:
            raise ValidationError("Invalid concession request status decision.")

        req = get_concession_request_for_update(self.request_id)
        if not req:
            raise ValidationError("Concession request not found.")
        if req.status != ConcessionStatus.PENDING:
            raise ValidationError("Concession request has already been decided.")

        update_concession_request(req, {
            "status": self.status, "approver": self.approver_user, "decided_at": timezone.now(),
        })

        if self.status == ConcessionStatus.APPROVED:
            for assignment in list_assignments_for_student(req.student_id):
                lines = list(assignment.discount_lines or [])
                if not any(d.get("request_id") == str(req.id) for d in lines):
                    components = assignment.structure_snapshot or []
                    base_paise = sum(int(c.get("amount_paise", 0)) for c in components)
                    amount = concession_amount_paise(req, base_paise=base_paise)
                    if amount <= 0 and req.rule and req.rule.percent:
                        amount = (base_paise * req.rule.percent) // 100
                    if amount > 0:
                        lines.append({
                            "request_id": str(req.id),
                            "label": req.rule.name if req.rule else "Concession",
                            "amount_paise": amount,
                        })
                        update_assignment(assignment, {"discount_lines": lines})
                        if req.amount_paise != amount:
                            update_concession_request(req, {"amount_paise": amount})

        return req
