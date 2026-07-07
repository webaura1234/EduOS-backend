"""Shared Payment -> FeePayment dict shaping — used by both the admin fees
overview aggregate and the dedicated paginated payments endpoint, so the two
stay byte-for-byte consistent."""

PAY_METHOD = {
    "razorpay": "upi",
    "bank_transfer": "upi",
    "cheque": "cash",
    "cash": "cash",
    "upi": "upi",
    "card": "card",
    "netbanking": "netbanking",
}
PAY_STATUS = {
    "captured": "captured", "failed": "failed", "refunded": "refunded",
    "created": "pending", "authorized": "pending", "pending": "pending",
}


def rupees(paise) -> float:
    return round((paise or 0) / 100, 2)


def student_name(enrollment) -> str:
    try:
        return enrollment.user.full_name
    except Exception:
        return ""


def batch_label(batch) -> str:
    if batch is None:
        return ""
    course = getattr(batch, "course", None)
    course_name = course.name if course else ""
    section = batch.name or ""
    if course_name and section:
        return f"{course_name} - {section}"
    return course_name or section


def class_label(enrollment) -> str:
    if not enrollment or not enrollment.current_batch_id:
        return ""
    return batch_label(enrollment.current_batch)


def payment_dict(p) -> dict:
    inv = p.invoice
    enrollment = inv.student if inv else None
    receipt = getattr(p, "receipt", None)
    return {
        "id": str(p.id),
        "studentId": str(enrollment.student_profile_id) if enrollment else "",
        "studentName": student_name(enrollment),
        "classLabel": class_label(enrollment),
        "paidAt": p.captured_at.isoformat() if p.captured_at else p.created_at.isoformat(),
        "amount": rupees(p.amount_paise),
        "amountPaise": p.amount_paise,
        "method": PAY_METHOD.get(p.method, "cash"),
        "reference": p.razorpay_payment_id or "",
        "receiptNo": str(receipt.sequence_number) if receipt else "",
        "orderId": p.razorpay_order_id or "",
        "status": PAY_STATUS.get(p.status, "pending"),
        "source": "gateway" if p.method == "razorpay" else "manual",
        "invoiceId": str(p.invoice_id) if p.invoice_id else "",
    }
