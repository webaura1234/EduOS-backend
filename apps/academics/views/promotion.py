"""Views — Academic year promotion workspace (Phase 1)."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.interactors import promotion as prom_i
from apps.academics.permissions import IsAdminOrSuperAdmin
from apps.academics.scoping import resolve_branch
from apps.academics.serializers.promotion import (
    PromotionBulkOverrideSerializer,
    PromotionDecisionsQuerySerializer,
    PromotionOverrideSerializer,
    PromotionReopenReviewSerializer,
    PromotionStartSerializer,
)


class PromotionCurrentView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response(prom_i.get_current_state(branch_id=branch.pk, tenant=request.user.tenant))


class PromotionStartView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = PromotionStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        from apps.academics.queries import calendar as cal_q
        from apps.academics.queries import promotion as prom_q

        source_year = cal_q.get_year(branch.pk, data["sourceYearId"])
        if source_year:
            existing = prom_q.get_draft_session(branch.pk, source_year.pk)
            if existing:
                counts = prom_q.count_by_final_action(existing.pk)
                return Response(
                    {
                        "code": "promotion_in_progress",
                        "detail": "A promotion review is already in progress.",
                        "session": prom_i.get_session_detail(branch_id=branch.pk, session_id=existing.pk),
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        result = prom_i.start_promotion(
            branch=branch,
            tenant=request.user.tenant,
            source_year_id=data["sourceYearId"],
            target_year_id=data.get("targetYearId"),
            target_year_create=data.get("targetYearCreate"),
            user=request.user,
        )
        return Response(result, status=status.HTTP_201_CREATED)


class PromotionSessionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(prom_i.get_session_detail(branch_id=branch.pk, session_id=session_id))


class PromotionDecisionsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        serializer = PromotionDecisionsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            prom_i.list_session_decisions(
                branch_id=branch.pk,
                session_id=session_id,
                branch_filter=data.get("branchId"),
                course_id=data.get("courseId"),
                batch_id=data.get("batchId"),
                action=data.get("action"),
                page=data.get("page", 1),
                page_size=data.get("pageSize", 50),
            )
        )


class PromotionDecisionOverrideView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, session_id, decision_id) -> Response:
        branch = resolve_branch(request)
        serializer = PromotionOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            prom_i.override_decision(
                branch_id=branch.pk,
                session_id=session_id,
                decision_id=decision_id,
                final_action=data["finalAction"],
                reason=data["reason"],
                user=request.user,
                request=request,
            )
        )


class PromotionDecisionBulkOverrideView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        serializer = PromotionBulkOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(
            prom_i.bulk_override_decisions(
                branch_id=branch.pk,
                session_id=session_id,
                final_action=data["finalAction"],
                reason=data["reason"],
                decision_ids=data.get("decisionIds"),
                filter_action=data.get("filterAction"),
                course_id=data.get("courseId"),
                batch_id=data.get("batchId"),
                user=request.user,
                request=request,
            )
        )


class PromotionApproveView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(
            prom_i.approve_promotion(
                branch_id=branch.pk,
                session_id=session_id,
                user=request.user,
                request=request,
            )
        )


class PromotionReopenReviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        serializer = PromotionReopenReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            prom_i.reopen_promotion_review(
                branch_id=branch.pk,
                session_id=session_id,
                reason=serializer.validated_data["reason"],
                user=request.user,
                request=request,
            )
        )
