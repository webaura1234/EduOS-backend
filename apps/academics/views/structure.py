"""Views — Department, Course, Batch."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.interactors import structure as struct_i
from apps.academics.permissions import IsAdminOrSuperAdmin
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import structure as struct_q
from apps.academics.scoping import resolve_branch
from apps.academics.serializers.structure import (
    BatchSerializer,
    CourseSerializer,
    CreateBatchSerializer,
    CreateCourseSerializer,
    CreateDepartmentSerializer,
    DepartmentSerializer,
    UpdateBatchSerializer,
    UpdateCourseSerializer,
    UpdateDepartmentSerializer,
)


def _map_fields(data, mapping):
    fields = {}
    for src, dst in mapping.items():
        if src in data:
            fields[dst] = data[src]
    return fields


class DepartmentListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        depts = struct_q.list_departments(branch.pk)
        return Response({"departments": DepartmentSerializer(depts, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = CreateDepartmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dept = struct_i.create_department(
            branch.pk, request.user.tenant_id,
            name=data["name"], code=data.get("code", ""),
            department_type=data.get("departmentType", "department"),
            head_faculty_id=data.get("headFacultyId"), user=request.user,
        )
        return Response({"department": DepartmentSerializer(dept).data}, status=status.HTTP_201_CREATED)


class DepartmentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, dept_id) -> Response:
        branch = resolve_branch(request)
        dept = struct_q.get_department(branch.pk, dept_id)
        if not dept:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateDepartmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = _map_fields(data, {
            "name": "name", "code": "code", "departmentType": "department_type",
            "headFacultyId": "head_faculty_id", "version": "version",
        })
        dept = struct_i.update_department(dept, request.user.tenant_id, fields=fields, user=request.user)
        return Response({"department": DepartmentSerializer(dept).data})

    def delete(self, request, dept_id) -> Response:
        branch = resolve_branch(request)
        dept = struct_q.get_department(branch.pk, dept_id)
        if not dept:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        struct_i.delete_department(dept, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CourseListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        dept_id = request.query_params.get("departmentId")
        courses = struct_q.list_courses(branch.pk, department_id=dept_id)
        return Response({"courses": CourseSerializer(courses, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        serializer = CreateCourseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dept = struct_q.get_department(branch.pk, data["departmentId"])
        if not dept:
            return Response({"error": "Department not found."}, status=status.HTTP_404_NOT_FOUND)
        course = struct_i.create_course(
            dept, name=data["name"], code=data.get("code", ""),
            duration_years=data.get("durationYears", 1),
            regulation=data.get("regulation", ""),
            total_credits=data.get("totalCredits"), user=request.user,
        )
        return Response({"course": CourseSerializer(course).data}, status=status.HTTP_201_CREATED)


class CourseDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, course_id) -> Response:
        branch = resolve_branch(request)
        course = struct_q.get_course(branch.pk, course_id)
        if not course:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateCourseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = _map_fields(data, {
            "name": "name", "code": "code", "durationYears": "duration_years",
            "regulation": "regulation", "totalCredits": "total_credits", "version": "version",
        })
        course = struct_i.update_course(course, fields=fields, user=request.user)
        return Response({"course": CourseSerializer(course).data})

    def delete(self, request, course_id) -> Response:
        branch = resolve_branch(request)
        course = struct_q.get_course(branch.pk, course_id)
        if not course:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        struct_i.delete_course(course, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class BatchListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        from apps.accounts.models.user import Role
        from apps.organizations.queries.branch import get_branch

        user = request.user
        if user.role == Role.SUPER_ADMIN:
            branch_id = request.query_params.get("branchId") or request.query_params.get("branch")
            if not branch_id or branch_id == "all":
                return Response(
                    {"error": "branchId is required for super admin."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            branch = get_branch(user.tenant_id, branch_id)
            if branch is None:
                return Response({"error": "Branch not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            branch = resolve_branch(request)
        batches = struct_q.list_batches(
            branch.pk,
            course_id=request.query_params.get("courseId"),
            academic_year_id=request.query_params.get("academicYearId"),
        )
        return Response({"batches": BatchSerializer(batches, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        serializer = CreateBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        course = struct_q.get_course(branch.pk, data["courseId"])
        if not course:
            return Response({"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND)
        year = cal_q.get_year(branch.pk, data["academicYearId"])
        if not year:
            return Response({"error": "Academic year not found."}, status=status.HTTP_404_NOT_FOUND)
        batch = struct_i.create_batch(
            request.user.tenant, course, year,
            name=data["name"], capacity=data.get("capacity", 40),
            class_teacher_id=data.get("classTeacherId"), user=request.user,
        )
        batch = struct_q.get_batch(branch.pk, batch.pk)
        return Response({"batch": BatchSerializer(batch).data}, status=status.HTTP_201_CREATED)


class BatchDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, batch_id) -> Response:
        branch = resolve_branch(request)
        batch = struct_q.get_batch(branch.pk, batch_id)
        if not batch:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"batch": BatchSerializer(batch).data})

    def patch(self, request, batch_id) -> Response:
        branch = resolve_branch(request)
        batch = struct_q.get_batch(branch.pk, batch_id)
        if not batch:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = _map_fields(data, {
            "name": "name", "capacity": "capacity",
            "classTeacherId": "class_teacher_id", "version": "version",
        })
        batch = struct_i.update_batch(request.user.tenant, batch, fields=fields, user=request.user)
        batch = struct_q.get_batch(branch.pk, batch.pk)
        return Response({"batch": BatchSerializer(batch).data})

    def delete(self, request, batch_id) -> Response:
        branch = resolve_branch(request)
        batch = struct_q.get_batch(branch.pk, batch_id)
        if not batch:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        struct_i.delete_batch(batch, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
