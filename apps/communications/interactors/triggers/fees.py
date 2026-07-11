"""Fee notification triggers."""

from django.db.models import F
from django.utils import timezone

from apps.communications.interactors.create import create_notification
from apps.communications.interactors.recipients import student_and_guardian_users
from apps.communications.queries import inbox as inbox_q
from apps.fees.models import FeeInvoice
from apps.organizations.models import TenantSettings


def _fee_reminder_days(tenant) -> list[int]:
    try:
        days = tenant.tenant_settings.fee_reminder_days
    except TenantSettings.DoesNotExist:
        days = []
    if not days:
        return [3]
    return sorted({int(d) for d in days if int(d) > 0}, reverse=True)


def _student_user(invoice):
    enrollment = invoice.student
    if enrollment and enrollment.student_profile_id:
        profile = enrollment.student_profile
        if profile and profile.user_id:
            return profile.user
    return None


def _format_amount(paise: int) -> str:
    return f"{paise / 100:,.0f}"


def notify_payment_received(invoice, payment, *, created_by=None) -> None:
    student_user = _student_user(invoice)
    if not student_user:
        return
    receipt_ref = str(getattr(payment, "id", payment))
    amount = _format_amount(getattr(payment, "amount_paise", invoice.paid_paise))
    name = student_user.full_name
    for user, extras in student_and_guardian_users(student_user):
        create_notification(
            "fee.payment_received",
            tenant=invoice.branch.tenant,
            branch=invoice.branch,
            recipient=user,
            variables={
                "student_name": name,
                "amount_paid": amount,
                "receipt_ref": receipt_ref,
                **extras,
            },
            dedup_key=f"fee:paid:{payment.pk}:{user.pk}",
            created_by=created_by,
            related_entity_type="invoice",
            related_entity_id=invoice.pk,
        )
    inbox_q.expire_fee_notifications_for_invoice(invoice.pk)


def run_fee_notification_scan() -> int:
    """Daily job — due reminders, due today, overdue."""
    today = timezone.localdate()
    count = 0
    open_invoices = FeeInvoice.objects.filter(
        is_active=True, total_paise__gt=F("paid_paise"),
    ).select_related(
        "branch", "branch__tenant",
        "student__student_profile__user",
    )

    for invoice in open_invoices:
        if not invoice.due_date:
            continue
        student_user = _student_user(invoice)
        if not student_user:
            continue
        balance = invoice.balance_paise
        if balance <= 0:
            continue
        amount = _format_amount(balance)
        name = student_user.full_name
        due_str = invoice.due_date.isoformat()
        days_until = (invoice.due_date - today).days
        tenant = invoice.branch.tenant

        if days_until > 0 and days_until in _fee_reminder_days(tenant):
            for user, extras in student_and_guardian_users(student_user):
                if create_notification(
                    "fee.due_reminder",
                    tenant=tenant,
                    branch=invoice.branch,
                    recipient=user,
                    variables={
                        "student_name": name,
                        "amount_due": amount,
                        "due_date": due_str,
                        "days_until_due": str(days_until),
                        **extras,
                    },
                    dedup_key=f"fee:due_reminder:{invoice.pk}:{days_until}:{user.pk}",
                    related_entity_type="invoice",
                    related_entity_id=invoice.pk,
                    due_date=invoice.due_date,
                ):
                    count += 1

        elif days_until == 0:
            for user, extras in student_and_guardian_users(student_user):
                if create_notification(
                    "fee.due_today",
                    tenant=tenant,
                    branch=invoice.branch,
                    recipient=user,
                    variables={
                        "student_name": name,
                        "amount_due": amount,
                        "due_date": due_str,
                        **extras,
                    },
                    dedup_key=f"fee:due_today:{invoice.pk}:{today}:{user.pk}",
                    related_entity_type="invoice",
                    related_entity_id=invoice.pk,
                    due_date=invoice.due_date,
                ):
                    count += 1

        elif days_until < 0:
            overdue_days = abs(days_until)
            for user, extras in student_and_guardian_users(student_user):
                if create_notification(
                    "fee.overdue",
                    tenant=tenant,
                    branch=invoice.branch,
                    recipient=user,
                    variables={
                        "student_name": name,
                        "amount_due": amount,
                        "due_date": due_str,
                        "days_overdue": str(overdue_days),
                        **extras,
                    },
                    dedup_key=f"fee:overdue:{invoice.pk}:{today}:{user.pk}",
                    related_entity_type="invoice",
                    related_entity_id=invoice.pk,
                    due_date=invoice.due_date,
                ):
                    count += 1
    return count
