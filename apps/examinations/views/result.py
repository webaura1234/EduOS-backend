"""Views — exam results compute, publish, revise, grace marks, analytics."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.examinations.interactors import result as result_i
from apps.examinations.permissions import IsAdminOrSuperAdmin
from apps.examinations.queries import exam as exam_q
from apps.examinations.serializers.result import (
    GraceMarksSerializer,
    PublishResultsSerializer,
    ReportCardSerializer,
    ResultPublishConfirmationSerializer,
    ResultPublicationSerializer,
    ResultsPreflightSerializer,
    ResultsStatusSerializer,
    ReviseResultsSerializer,
    ResultsAnalyticsSerializer,
    StudentResultSerializer,
)


class ExamResultsComputeView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        payload = result_i.compute_results(exam, branch=branch, tenant=request.user.tenant)
        return Response(
            {"confirmation": ResultPublishConfirmationSerializer(payload).data},
            status=status.HTTP_200_OK,
        )


class ExamResultsPublishView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = PublishResultsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = result_i.publish_results(
            exam,
            branch=branch,
            tenant=request.user.tenant,
            confirm_token=data.get("confirmToken") or None,
            note=data.get("note", ""),
            user=request.user,
        )
        return Response(
            {
                "publication": ResultPublicationSerializer(payload["publication"]).data,
                "studentResults": StudentResultSerializer(payload["studentResults"], many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class ExamResultsReviseView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ReviseResultsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = result_i.revise_results(
            exam,
            branch=branch,
            tenant=request.user.tenant,
            note=data.get("note", ""),
            user=request.user,
        )
        return Response(
            {
                "publication": ResultPublicationSerializer(payload["publication"]).data,
                "studentResults": StudentResultSerializer(payload["studentResults"], many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class ExamGraceMarksView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = GraceMarksSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entries = [
            {
                "student_id": e["studentId"],
                "subject_id": e["subjectId"],
                "grace_marks": e["graceMarks"],
            }
            for e in serializer.validated_data["entries"]
        ]
        payload = result_i.apply_grace_marks(
            exam,
            tenant=request.user.tenant,
            entries=entries,
            user=request.user,
        )
        return Response(payload, status=status.HTTP_200_OK)


class ExamAnalyticsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        analytics = result_i.get_exam_analytics(exam, tenant=request.user.tenant)
        return Response({"analytics": ResultsAnalyticsSerializer(analytics).data})


class ExamResultsPreflightView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        payload = result_i.preflight_results(exam, branch=branch)
        return Response({"preflight": ResultsPreflightSerializer(payload).data})


class ExamResultsStatusView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        payload = result_i.get_results_status(exam)
        return Response({"status": ResultsStatusSerializer(payload).data})


class ExamReportCardView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        student_id = request.query_params.get("studentId")
        if not student_id:
            return Response({"error": "studentId is required."}, status=status.HTTP_400_BAD_REQUEST)
        from apps.academics.helpers import is_college

        payload = result_i.download_report_card(
            exam,
            branch=branch,
            student_profile_id=student_id,
            college=is_college(request.user.tenant),
        )
        return Response({"reportCard": ReportCardSerializer(payload).data})


class ExamResultsExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        class_section_id = request.query_params.get("classSectionId")
        if not class_section_id:
            return Response(
                {"error": "classSectionId is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        csv_text = result_i.export_class_results_csv(
            exam,
            branch_id=branch.pk,
            class_section_id=class_section_id,
        )
        from django.http import HttpResponse

        filename = f"{exam.name.replace(' ', '-')}-{class_section_id}-results.csv"
        response = HttpResponse(csv_text, content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
