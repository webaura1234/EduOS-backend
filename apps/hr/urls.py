"""URL configuration for the hr app."""

from django.urls import path

from apps.hr.views.overview import AdminHROverviewView
from apps.hr.views.employee import (
    BranchAssignView,
    EmployeeDeactivateView,
    EmployeeListCreateView,
)
from apps.hr.views.my_leave import FacultyMyLeaveView
from apps.hr.views.leave import (
    LeaveApplyView,
    LeaveBalancesView,
    LeaveDecideView,
    LeaveListView,
)
from apps.hr.views.faculty_payslip import FacultyPayslipView
from apps.hr.views.payroll import (
    MyPayslipsView,
    PayrollAdjustmentView,
    PayrollRunCreateView,
    PayrollRunDetailView,
    PayrollRunLockView,
    PayslipDetailView,
    PayslipListView,
    SalaryComponentListCreateView,
)

app_name = "hr"

urlpatterns = [
    # Admin aggregate overview (HrData shape)
    path("admin-overview/", AdminHROverviewView.as_view(), name="admin-overview"),

    # Employees
    path("employees/", EmployeeListCreateView.as_view(), name="employee-list"),
    path("employees/<uuid:employee_id>/deactivate/", EmployeeDeactivateView.as_view(),
         name="employee-deactivate"),
    path("employees/<uuid:employee_id>/leave-balances/", LeaveBalancesView.as_view(),
         name="employee-leave-balances"),
    path("branch-faculty/", BranchAssignView.as_view(), name="branch-assign"),

    # Leave
    path("leave/", LeaveApplyView.as_view(), name="leave-apply"),
    path("me/leave/", FacultyMyLeaveView.as_view(), name="my-leave"),
    path("leave/list/", LeaveListView.as_view(), name="leave-list"),
    path("leave/<uuid:application_id>/decide/", LeaveDecideView.as_view(), name="leave-decide"),

    # Payroll
    path("salary-components/", SalaryComponentListCreateView.as_view(), name="salary-components"),
    path("payroll/runs/", PayrollRunCreateView.as_view(), name="payroll-run"),
    path("payroll/runs/<uuid:run_id>/", PayrollRunDetailView.as_view(), name="payroll-run-detail"),
    path("payroll/runs/<uuid:run_id>/lock/", PayrollRunLockView.as_view(), name="payroll-run-lock"),
    path("payroll/runs/<uuid:run_id>/payslips/", PayslipListView.as_view(), name="payslip-list"),
    path("payroll/adjustments/", PayrollAdjustmentView.as_view(), name="payroll-adjustment"),
    path("payslips/<uuid:payslip_id>/", PayslipDetailView.as_view(), name="payslip-detail"),
    path("me/payslips/", MyPayslipsView.as_view(), name="my-payslips"),
    path("me/payslip/", FacultyPayslipView.as_view(), name="faculty-payslip"),
]
