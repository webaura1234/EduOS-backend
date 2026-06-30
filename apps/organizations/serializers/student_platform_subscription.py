"""Presenters for student platform subscription API responses."""

from apps.organizations.models import StudentPlatformSubscription


def subscription_row_dict(row: StudentPlatformSubscription) -> dict:
    user = row.student_user
    tenant = row.tenant
    branch = row.branch
    return {
        "id": str(row.id),
        "tenantId": str(tenant.id),
        "tenantName": tenant.name,
        "subdomain": tenant.subdomain,
        "branchId": str(branch.id),
        "branchName": branch.name,
        "studentUserId": str(user.id),
        "studentName": user.full_name,
        "loginId": user.custom_login_id or "",
        "plan": row.plan,
        "academicYear": row.academic_year,
        "annualFeeInr": row.annual_fee_inr,
        "status": row.status,
        "paidAt": row.paid_at.isoformat() if row.paid_at else None,
    }
