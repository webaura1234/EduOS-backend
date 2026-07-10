"""Fee head master CRUD views."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.fees.models import FeeHead
from apps.fees.serializers.fee_head import FeeHeadSerializer
from apps.fees.views.v1.views import get_request_branch


class FeeHeadViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    serializer_class = FeeHeadSerializer

    def get_queryset(self):
        branch = get_request_branch(self.request)
        return FeeHead.objects.filter(branch_id=branch.id, is_active=True).order_by("name")

    def perform_create(self, serializer):
        branch = get_request_branch(self.request)
        try:
            serializer.save(branch=branch, created_by=self.request.user, updated_by=self.request.user)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete(user=self.request.user)
