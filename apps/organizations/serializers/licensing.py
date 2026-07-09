"""Dict serializers for the licensing module (platform + tenant dashboards)."""

from apps.organizations.models import (
    LicenseInvoice,
    LicensePayment,
    StudentLicense,
    TenantLicenseSummary,
    TenantSubscriptionPeriod,
)


def period_dict(period: TenantSubscriptionPeriod | None) -> dict | None:
    if period is None:
        return None
    return {
        "id": str(period.id),
        "startDate": period.start_date.isoformat(),
        "endDate": period.end_date.isoformat(),
        "status": period.status,
        "pricePerStudentInr": period.price_per_student_inr,
        "graceEndsAt": period.grace_ends_at.isoformat() if period.grace_ends_at else None,
    }


def summary_dict(summary: TenantLicenseSummary, *, unit_price: int) -> dict:
    annual = summary.annual_subscription_inr
    collected = summary.collected_subscription_inr
    return {
        "licensesPurchased": summary.licenses_purchased,
        "licensesConsumed": summary.licenses_consumed,
        "unlicensedStudents": summary.unlicensed_active_count,
        "pendingAmountInr": summary.pending_amount_inr,
        "unitPriceInr": unit_price,
        "activeStudentCount": summary.active_student_count,
        "annualSubscriptionInr": annual,
        "collectedSubscriptionInr": collected,
        "outstandingInr": max(0, annual - collected),
        "period": period_dict(summary.current_period),
    }


def payment_dict(payment: LicensePayment) -> dict:
    return {
        "id": str(payment.id),
        "tenantId": str(payment.tenant_id),
        "branchId": str(payment.branch_id) if payment.branch_id else None,
        "branchName": payment.branch.name if payment.branch_id else None,
        "licensesGranted": payment.licenses_granted,
        "amountInr": payment.amount_inr,
        "paymentMode": payment.payment_mode,
        "referenceNumber": payment.reference_number,
        "paidAt": payment.paid_at.isoformat(),
        "notes": payment.notes,
        "recordedBy": (
            payment.recorded_by.full_name if payment.recorded_by_id else "Platform Owner"
        ),
        "createdAt": payment.created_at.isoformat(),
    }


def invoice_dict(invoice: LicenseInvoice) -> dict:
    return {
        "id": str(invoice.id),
        "tenantId": str(invoice.tenant_id),
        "invoiceType": invoice.invoice_type,
        "licensesCount": invoice.licenses_count,
        "unitPriceInr": invoice.unit_price_inr,
        "amountInr": invoice.amount_inr,
        "status": invoice.status,
        "issuedAt": invoice.issued_at.isoformat() if invoice.issued_at else None,
        "notes": invoice.notes,
    }


def student_license_dict(row: StudentLicense) -> dict:
    user = row.student_user
    return {
        "id": str(row.id),
        "studentUserId": str(row.student_user_id) if row.student_user_id else None,
        "studentName": (user.full_name if user else "") or row.student_name,
        "admissionNumber": user.custom_login_id if user else None,
        "branchId": str(row.branch_id) if row.branch_id else None,
        "branchName": row.branch.name if row.branch_id else None,
        "enrolledAt": row.enrolled_at.isoformat(),
        "licenseStatus": row.license_status,
        "licensedAt": row.licensed_at.isoformat() if row.licensed_at else None,
        "isActive": bool(user and user.is_active),
    }
