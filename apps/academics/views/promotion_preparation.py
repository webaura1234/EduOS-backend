"""Views — Promotion preparation (Phase 2)."""

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.academics.interactors import promotion_preparation as prep_i
from apps.academics.interactors import promotion_validation as val_i
from apps.academics.permissions import IsAdminOrSuperAdmin
from apps.academics.scoping import resolve_branch
from apps.academics.serializers.promotion_preparation import (
    BlockedStudentsQuerySerializer,
    ClassMappingsPatchSerializer,
    PreparationUnlockSerializer,
    SectionMappingsPatchSerializer,
)


class PromotionPreparationView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(prep_i.get_preparation_state(branch_id=branch.pk, session_id=session_id))


class PromotionPreparationStartView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(prep_i.start_preparation(branch_id=branch.pk, session_id=session_id, user=request.user))


class PromotionPreparationReadinessView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(prep_i.get_readiness_audit(branch_id=branch.pk, session_id=session_id))


class PromotionClassMappingsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(prep_i.list_class_mappings(branch_id=branch.pk, session_id=session_id))

    def patch(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        serializer = ClassMappingsPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            prep_i.update_class_mappings(
                branch_id=branch.pk,
                session_id=session_id,
                mappings=serializer.validated_data["mappings"],
                user=request.user,
            )
        )


class PromotionSectionMappingsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(
            prep_i.list_section_mappings(
                branch_id=branch.pk,
                session_id=session_id,
                course_id=request.query_params.get("courseId"),
                page=int(request.query_params.get("page", 1)),
                page_size=int(request.query_params.get("pageSize", 50)),
            )
        )

    def patch(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        serializer = SectionMappingsPatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            prep_i.update_section_mappings(
                branch_id=branch.pk,
                session_id=session_id,
                assignments=serializer.validated_data["assignments"],
                user=request.user,
            )
        )


class PromotionValidateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(
            val_i.run_validation(branch_id=branch.pk, session_id=session_id, user=request.user)
        )


class PromotionPreviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(val_i.get_preview(branch_id=branch.pk, session_id=session_id))


class PromotionBlockedStudentsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        serializer = BlockedStudentsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            val_i.list_blocked_students(
                branch_id=branch.pk,
                session_id=session_id,
                page=data.get("page", 1),
                page_size=data.get("pageSize", 50),
            )
        )


class PromotionPreparationLockView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(
            prep_i.lock_preparation(
                branch_id=branch.pk,
                session_id=session_id,
                user=request.user,
                request=request,
            )
        )


class PromotionPreparationUnlockView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        serializer = PreparationUnlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            prep_i.unlock_preparation(
                branch_id=branch.pk,
                session_id=session_id,
                reason=serializer.validated_data["reason"],
                user=request.user,
                request=request,
            )
        )
