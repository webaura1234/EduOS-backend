"""HR export definitions."""

from apps.accounts.models.user import Role
from apps.analytics.enums import ReportType
from apps.core.exports.base import AggregationExportDefinition, Column
from apps.core.exports.registry import register
from apps.hr.queries import employee as emp_q


class HrHeadcountExport(AggregationExportDefinition):
    report_type = ReportType.HR_HEADCOUNT
    title = "HR Headcount"
    module = "hr"
    description = "Active employees by type and department"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    supports_preview = True
    estimated_runtime = "instant"
    sync_threshold = 500

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("employeeCode", "Employee ID"),
            Column("name", "Employee Name"),
            Column("role", "Role"),
            Column("designation", "Designation"),
            Column("employmentType", "Employment Type"),
            Column("joinedAt", "Joined At", format="date"),
        ]

    def resolve_rows(self, *, tenant, branch, params: dict) -> list[dict]:
        rows = []
        for emp in emp_q.list_employees(branch.pk, active_only=True):  # Only show active for headcount unless they want inactive
            user = emp.user
            rows.append({
                "employeeCode": emp.employee_code,
                "name": user.full_name if user else "",
                "role": user.get_role_display() if user else "",
                "employmentType": emp.get_employment_type_display(),
                "designation": emp.designation or "",
                "joinedAt": emp.joined_at.isoformat() if emp.joined_at else "",
            })
        return rows


def register_all() -> None:
    register(HrHeadcountExport())


register_all()
