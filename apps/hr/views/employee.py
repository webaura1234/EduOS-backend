"""Views — employee master + multi-branch assignment (thin; ORM stays in queries)."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.accounts.queries.user import get_user_by_id
from apps.hr.interactors import employee as emp_i
from apps.hr.queries import employee as emp_q
from apps.hr.serializers.employee import (
    AssignBranchSerializer,
    BranchFacultySerializer,
    CreateEmployeeSerializer,
    DeactivateEmployeeSerializer,
    EmployeeSerializer,
)


def _step_up_ok(request) -> bool:
    return request.headers.get("X-Step-Up-Verified") == "true"


class EmployeeListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        active = request.query_params.get("active", "true") != "false"
        rows = emp_q.list_employees(branch.pk, active_only=active)
        return Response({"employees": EmployeeSerializer(rows, many=True).data})

    def post(self, request):
        branch = resolve_branch(request)
        s = CreateEmployeeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        user_obj = get_user_by_id(data["userId"])
        if not user_obj or str(user_obj.tenant_id) != str(request.user.tenant_id):
            return Response({"userId": "User not found in your institution."},
                            status=http.HTTP_404_NOT_FOUND)
        emp = emp_i.create_employee(
            branch=branch, user_obj=user_obj, employee_code=data["employeeCode"],
            employment_type=data["employmentType"], joined_at=data["joinedAt"],
            designation=data["designation"], base_components=data["baseComponents"],
            bank_account=data["bankAccount"], ifsc=data["ifsc"], pan=data["pan"],
            actor=request.user,
        )
        return Response({"employee": EmployeeSerializer(emp).data}, status=http.HTTP_201_CREATED)


class EmployeeDeactivateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, employee_id):
        if not _step_up_ok(request):
            return Response({"code": "step_up_required", "action": "employee.deactivate"},
                            status=http.HTTP_403_FORBIDDEN)
        branch = resolve_branch(request)
        emp = emp_q.get_employee(branch.pk, employee_id)
        if not emp:
            return Response({"error": "Employee not found."}, status=http.HTTP_404_NOT_FOUND)
        s = DeactivateEmployeeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        emp = emp_i.deactivate_employee(employee=emp, exited_at=s.validated_data.get("exitedAt"),
                                        actor=request.user)
        return Response({"employee": EmployeeSerializer(emp).data})


class BranchAssignView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        s = AssignBranchSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        faculty = get_user_by_id(data["facultyId"])
        branch = resolve_branch(request, branch_id=data["branchId"])
        if not faculty or str(faculty.tenant_id) != str(request.user.tenant_id):
            return Response({"facultyId": "Faculty not found."}, status=http.HTTP_404_NOT_FOUND)
        bf = emp_i.assign_branch(
            faculty_user=faculty, branch=branch, is_salary_branch=data["isSalaryBranch"],
            role_at_branch=data["roleAtBranch"], actor=request.user,
        )
        return Response({"assignment": BranchFacultySerializer(bf).data},
                        status=http.HTTP_201_CREATED)
