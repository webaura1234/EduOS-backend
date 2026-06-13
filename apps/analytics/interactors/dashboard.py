"""Interactors — role dashboards (read aggregates).

Composes the other modules through THEIR query/interactor layers — analytics adds no
cross-app ORM (architecture rule). Computed live per request (OD-1); the view stamps
`X-Cache-Age` / `lastUpdated`.
"""

from apps.accounts.queries.user import count_active_by_role_in_tenant
from apps.accounts.models.user import Role
from apps.admissions.queries.enquiry import funnel_counts
from apps.attendance.interactors import report as att_report
from apps.fees.interactors.report import GetCollectionDashboardInteractor
from apps.fees.queries.defaulter import list_defaulters
from apps.hr.queries.leave import leave_summary
from apps.organizations.queries.branch import list_branches


def collection_dashboard(branch) -> dict:
    """F-138 — real-time fee collection metrics for a branch."""
    return GetCollectionDashboardInteractor(branch.pk).execute()


def admin_dashboard(branch, tenant) -> dict:
    """F-051 / F-053 — admin snapshot + alerts for one branch."""
    fees = GetCollectionDashboardInteractor(branch.pk).execute()
    shortage = att_report.shortage_report(branch)
    defaulters = list(list_defaulters(branch.pk))
    return {
        "fees": fees,
        "alerts": {
            "lowAttendanceCount": len(shortage["rows"]),
            "lowAttendance": shortage["rows"][:10],
            "pendingFeesCount": len(defaulters),
            "attendanceThreshold": shortage["threshold"],
        },
        "admissionsFunnel": funnel_counts(branch.pk),
        "leaveSummary": leave_summary(branch.pk),
    }


def super_admin_dashboard(tenant) -> dict:
    """F-021/022/025/038/039 — consolidated + per-branch comparison across the tenant."""
    branches = list(list_branches(tenant.pk))
    per_branch = []
    total_collected = total_invoiced = total_low_attendance = 0
    consolidated_defaulters = []
    for b in branches:
        fees = GetCollectionDashboardInteractor(b.pk).execute()
        shortage = att_report.shortage_report(b)
        defaulters = list(list_defaulters(b.pk))
        total_collected += fees["totalCollectedPaise"]
        total_invoiced += fees["totalInvoicedPaise"]
        total_low_attendance += len(shortage["rows"])
        consolidated_defaulters.append({"branchId": str(b.pk), "branchName": b.name,
                                        "defaulterCount": len(defaulters)})
        per_branch.append({
            "branchId": str(b.pk),
            "branchName": b.name,
            "collectedPaise": fees["totalCollectedPaise"],
            "pendingPaise": fees["totalPendingPaise"],
            "lowAttendanceCount": len(shortage["rows"]),
        })
    return {
        "totals": {
            "branches": len(branches),
            "students": count_active_by_role_in_tenant(tenant.pk, Role.STUDENT),
            "faculty": count_active_by_role_in_tenant(tenant.pk, Role.FACULTY),
            "collectedPaise": total_collected,
            "invoicedPaise": total_invoiced,
            "pendingPaise": max(total_invoiced - total_collected, 0),
            "lowAttendanceCount": total_low_attendance,
        },
        "branchComparison": per_branch,
        "consolidatedDefaulters": consolidated_defaulters,
    }
