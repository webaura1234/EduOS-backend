"""Views — Course Merit List and Waitlist management."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.admissions.interactors import merit_list as merit_i
from apps.admissions.queries import application as app_q
from apps.admissions.serializers.application import ApplicationSerializer, WaitlistSerializer


class CourseMeritListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, course_id) -> Response:
        branch = resolve_branch(request)
        ranked_apps = merit_i.get_merit_list(branch_id=branch.pk, course_id=course_id)
        return Response({"meritList": ApplicationSerializer(ranked_apps, many=True).data})


class WaitlistListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        course_id = request.query_params.get("courseId")
        entries = app_q.list_waitlist(branch.pk, course_id=course_id)
        return Response({"waitlist": WaitlistSerializer(entries, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        application_id = request.data.get("applicationId")
        rank = request.data.get("rank")
        if not application_id or rank is None:
            return Response({"error": "applicationId and rank are required."}, status=status.HTTP_400_BAD_REQUEST)
        
        application = app_q.get_application(branch.pk, application_id)
        if not application:
            return Response({"error": "Application not found."}, status=status.HTTP_404_NOT_FOUND)
            
        entry = merit_i.add_to_waitlist(
            branch=branch,
            application=application,
            rank=int(rank),
            user=request.user,
        )
        return Response({"waitlist": WaitlistSerializer(entry).data}, status=status.HTTP_201_CREATED)


class WaitlistPromoteView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, waitlist_id) -> Response:
        branch = resolve_branch(request)
        application = merit_i.promote_waitlist_entry(
            branch_id=branch.pk,
            waitlist_entry_id=waitlist_id,
            user=request.user,
        )
        return Response({"application": ApplicationSerializer(application).data})
