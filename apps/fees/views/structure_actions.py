"""Fee structure lifecycle action views."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.fees.interactors.publish import (
    archive_fee_structure,
    create_new_structure_version,
    publish_fee_structure,
    structure_impact,
)
from apps.fees.queries.structure import get_structure
from apps.fees.views.admin_overview import _structure
from apps.fees.views.v1.views import get_request_branch


class FeeStructureImpactView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, structure_id):
        branch = get_request_branch(request)
        structure = get_structure(branch.id, structure_id)
        if not structure:
            return Response({"error": "Structure not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(structure_impact(structure))


class FeeStructurePublishView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, structure_id):
        branch = get_request_branch(request)
        structure = get_structure(branch.id, structure_id)
        if not structure:
            return Response({"error": "Structure not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            published = publish_fee_structure(structure=structure, user=request.user)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(_structure(published))


class FeeStructureArchiveView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, structure_id):
        branch = get_request_branch(request)
        structure = get_structure(branch.id, structure_id)
        if not structure:
            return Response({"error": "Structure not found."}, status=status.HTTP_404_NOT_FOUND)
        force = bool(request.data.get("force"))
        try:
            archived = archive_fee_structure(structure=structure, user=request.user, force=force)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(_structure(archived))


class FeeStructureNewVersionView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, structure_id):
        branch = get_request_branch(request)
        structure = get_structure(branch.id, structure_id)
        if not structure:
            return Response({"error": "Structure not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            new_structure = create_new_structure_version(structure=structure, user=request.user)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(_structure(new_structure), status=status.HTTP_201_CREATED)
