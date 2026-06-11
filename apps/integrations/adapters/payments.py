"""
Payment gateway adapter (Razorpay) with a deterministic sandbox.

This is the ONLY code that talks to Razorpay. It never touches the database —
fee bookkeeping lives entirely in apps.fees.queries.

Select the implementation with settings.PAYMENTS_GATEWAY_MODE = "sandbox" | "live".
Every Phase-1 test runs in sandbox (no network, no keys required).
"""

import hashlib
import hmac
import json
import uuid

from django.conf import settings


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class SandboxGateway:
    """Deterministic fake gateway for dev/test."""

    def create_order(self, *, amount_paise: int, receipt: str, notes: dict | None = None) -> dict:
        return {"order_id": f"order_sandbox_{uuid.uuid4().hex[:18]}", "amount": amount_paise, "currency": "INR"}

    def fetch_payment(self, payment_id: str) -> dict:
        # In sandbox, any referenced payment is treated as captured.
        return {"id": payment_id, "status": "captured"}

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        expected = _sign(body, settings.RAZORPAY_WEBHOOK_SECRET)
        return hmac.compare_digest(expected, signature or "")

    def sign_webhook(self, payload: dict) -> tuple[bytes, str]:
        """Helper used by tests to produce a validly-signed webhook body."""
        body = json.dumps(payload, separators=(",", ":")).encode()
        return body, _sign(body, settings.RAZORPAY_WEBHOOK_SECRET)

    def create_refund(self, *, payment_id: str, amount_paise: int) -> dict:
        return {"refund_id": f"rfnd_sandbox_{uuid.uuid4().hex[:16]}", "status": "processed"}


class RazorpayGateway:
    """Live Razorpay implementation (activated when PAYMENTS_GATEWAY_MODE=live)."""

    def create_order(self, *, amount_paise: int, receipt: str, notes: dict | None = None) -> dict:
        import razorpay
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        order = client.order.create({"amount": amount_paise, "currency": "INR",
                                     "receipt": receipt, "notes": notes or {}})
        return {"order_id": order["id"], "amount": order["amount"], "currency": order["currency"]}

    def fetch_payment(self, payment_id: str) -> dict:
        import razorpay
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        return client.payment.fetch(payment_id)

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        expected = _sign(body, settings.RAZORPAY_WEBHOOK_SECRET)
        return hmac.compare_digest(expected, signature or "")

    def create_refund(self, *, payment_id: str, amount_paise: int) -> dict:
        import razorpay
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        refund = client.payment.refund(payment_id, {"amount": amount_paise})
        return {"refund_id": refund["id"], "status": refund["status"]}


def get_gateway():
    """Return the active payment gateway per settings.PAYMENTS_GATEWAY_MODE."""
    if getattr(settings, "PAYMENTS_GATEWAY_MODE", "sandbox") == "live":
        return RazorpayGateway()
    return SandboxGateway()
