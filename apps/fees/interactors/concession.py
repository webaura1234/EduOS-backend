"""Concession interactors."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.fees.enums import StudentConcessionStatus
from apps.fees.models import ConcessionRule, StudentConcession
from apps.fees.queries.concession import (
    create_concession_rule,
    create_student_concession,
    get_concession_rule,
    get_student_concession_for_update,
    has_active_concession_for_profile,
    update_concession_rule,
    update_student_concession,
)
from apps.fees.services.concession_sync import assert_concession_modifiable, sync_student_concessions


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
        self._validate()
        return create_concession_rule(
            branch=self.branch, name=self.name, amount_paise=self.amount_paise,
            percent=self.percent, criteria=self.criteria, user=self.user,
        )

    def _validate(self) -> None:
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


class UpdateConcessionRuleInteractor:
    """Updates an existing concession rule through validated interactor."""

    def __init__(self, rule, name=None, amount_paise=None, percent=None, criteria=None, is_active=None, user=None):
        self.rule = rule
        self.name = name
        self.amount_paise = amount_paise
        self.percent = percent
        self.criteria = criteria
        self.is_active = is_active
        self.user = user

    def execute(self) -> ConcessionRule:
        fields = {}
        if self.name is not None:
            fields["name"] = self.name
        if self.amount_paise is not None:
            fields["amount_paise"] = self.amount_paise
        if self.percent is not None:
            fields["percent"] = self.percent
        if self.criteria is not None:
            fields["criteria"] = self.criteria
        if self.is_active is not None:
            fields["is_active"] = self.is_active

        name = fields.get("name", self.rule.name)
        amount = fields.get("amount_paise", self.rule.amount_paise)
        percent = fields.get("percent", self.rule.percent)
        CreateConcessionRuleInteractor(
            branch=self.rule.branch, name=name, amount_paise=amount, percent=percent,
        )._validate()

        return update_concession_rule(self.rule, fields, user=self.user)


class ApplyStudentConcessionInteractor:
    """Applies a concession rule directly to a student."""

    def __init__(self, branch, student, rule_id, reason, user):
        self.branch = branch
        self.student = student
        self.rule_id = rule_id
        self.reason = reason
        self.user = user

    @transaction.atomic
    def execute(self) -> StudentConcession:
        if not self.reason or not str(self.reason).strip():
            raise ValidationError("Reason is required.")

        rule = get_concession_rule(self.branch.id, self.rule_id)
        if rule is None:
            raise ValidationError("Concession rule not found.")
        if not rule.is_active:
            raise ValidationError("Concession rule is inactive.")

        profile_id = self.student.student_profile_id
        if StudentConcession.objects.select_for_update().filter(
            branch_id=self.branch.id,
            student__student_profile_id=profile_id,
            rule_id=rule.id,
            status=StudentConcessionStatus.ACTIVE,
            is_active=True,
        ).exists():
            raise ValidationError("Student already has an active concession for this rule.")

        assert_concession_modifiable(self.student.id)

        amount_paise = rule.amount_paise if rule.amount_paise else 1
        now = timezone.now()
        concession = create_student_concession(
            branch=self.branch,
            student=self.student,
            rule=rule,
            amount_paise=amount_paise,
            requested_by=self.user,
            approver=self.user,
            decided_at=now,
            note=self.reason.strip(),
            status=StudentConcessionStatus.ACTIVE,
            user=self.user,
        )
        sync_student_concessions(self.student.id, user=self.user)
        return concession


class BulkApplyStudentConcessionInteractor:
    """Applies a rule to multiple students; collects per-student skip reasons."""

    SKIP_ALREADY_ACTIVE = "Already has active concession"
    SKIP_INVOICE_PAID = "Invoice fully paid"
    SKIP_RULE_INACTIVE = "Rule inactive or not found"
    SKIP_NOT_FOUND = "Student not found in branch"

    def __init__(self, branch, student_ids, rule_id, reason, user):
        self.branch = branch
        self.student_ids = student_ids
        self.rule_id = rule_id
        self.reason = reason
        self.user = user

    def execute(self) -> dict:
        from apps.fees.queries.structure import get_student_in_branch

        rule = get_concession_rule(self.branch.id, self.rule_id)
        if rule is None or not rule.is_active:
            raise ValidationError("Concession rule not found or inactive.")
        if not self.reason or not str(self.reason).strip():
            raise ValidationError("Reason is required.")

        applied = []
        skipped = []
        seen_profiles: set[str] = set()
        for sid in self.student_ids:
            student = get_student_in_branch(self.branch.id, sid)
            if not student:
                skipped.append({"studentId": str(sid), "reason": self.SKIP_NOT_FOUND})
                continue
            profile_key = str(student.student_profile_id)
            if profile_key in seen_profiles:
                skipped.append({"studentId": str(sid), "reason": self.SKIP_ALREADY_ACTIVE})
                continue
            seen_profiles.add(profile_key)
            if has_active_concession_for_profile(
                branch_id=self.branch.id,
                profile_id=student.student_profile_id,
                rule_id=rule.id,
            ):
                skipped.append({"studentId": str(sid), "reason": self.SKIP_ALREADY_ACTIVE})
                continue
            try:
                assert_concession_modifiable(student.id)
            except ValidationError:
                skipped.append({"studentId": str(sid), "reason": self.SKIP_INVOICE_PAID})
                continue
            try:
                conc = ApplyStudentConcessionInteractor(
                    branch=self.branch,
                    student=student,
                    rule_id=rule.id,
                    reason=self.reason,
                    user=self.user,
                ).execute()
                applied.append(str(conc.id))
            except ValidationError as exc:
                skipped.append({"studentId": str(sid), "reason": "; ".join(exc.messages)})

        return {"applied": applied, "skipped": skipped}


class RevokeStudentConcessionInteractor:
    """Revokes an active student concession."""

    def __init__(self, concession_id, reason, user):
        self.concession_id = concession_id
        self.reason = reason
        self.user = user

    @transaction.atomic
    def execute(self) -> StudentConcession:
        if not self.reason or not str(self.reason).strip():
            raise ValidationError("Reason is required.")

        conc = get_student_concession_for_update(self.concession_id)
        if not conc:
            raise ValidationError("Student concession not found.")
        if conc.status != StudentConcessionStatus.ACTIVE:
            raise ValidationError("Only active concessions can be revoked.")

        update_student_concession(conc, {
            "status": StudentConcessionStatus.REVOKED,
            "note": self.reason.strip(),
            "decided_at": timezone.now(),
            "approver": self.user,
        }, user=self.user)
        sync_student_concessions(conc.student_id, user=self.user)
        return conc


class EditStudentConcessionInteractor:
    """Edits the amount on an active student concession."""

    def __init__(self, concession_id, amount_paise, user):
        self.concession_id = concession_id
        self.amount_paise = amount_paise
        self.user = user

    @transaction.atomic
    def execute(self) -> StudentConcession:
        if self.amount_paise <= 0:
            raise ValidationError("Concession amount must be greater than zero.")

        conc = get_student_concession_for_update(self.concession_id)
        if not conc:
            raise ValidationError("Student concession not found.")
        if conc.status != StudentConcessionStatus.ACTIVE:
            raise ValidationError("Only active concessions can be edited.")

        assert_concession_modifiable(conc.student_id)
        update_student_concession(conc, {"amount_paise": self.amount_paise}, user=self.user)
        sync_student_concessions(conc.student_id, user=self.user)
        return conc


# Backward-compatible alias for legacy imports only.
CreateConcessionRequestInteractor = ApplyStudentConcessionInteractor
