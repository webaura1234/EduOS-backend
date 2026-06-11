"""Queries — WebhookEventLog."""

from django.utils import timezone

from apps.fees.models import WebhookEventLog


def get_webhook_log(event_id) -> WebhookEventLog | None:
    try:
        return WebhookEventLog.objects.get(event_id=event_id, is_active=True)
    except WebhookEventLog.DoesNotExist:
        return None


def create_webhook_log(*, event_id, razorpay_payment_id="", payload=None, processed_at=None) -> WebhookEventLog:
    if processed_at is None:
        processed_at = timezone.now()
    return WebhookEventLog.objects.create(
        event_id=event_id,
        razorpay_payment_id=razorpay_payment_id,
        payload=payload or {},
        processed_at=processed_at,
    )
