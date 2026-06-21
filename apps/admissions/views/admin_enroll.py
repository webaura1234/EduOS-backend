"""Admin: enroll a student directly from an application.

The frontend enroll is a one-click action — it doesn't collect the full provisioning
form. This endpoint derives what it can from the application/enquiry (name, DOB,
parent name), auto-generates an admission number, and picks a batch (override via
batchId), then runs the standard provisioning interactor. Duplicate / linked-account
conditions are surfaced as 409s the UI can confirm and retry.
"""

import uuid

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries.calendar import get_current_year
from apps.academics.queries.structure import list_batches
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.admissions.interactors.enrollment import (
    DuplicateStudentError,
    LinkedAccountWarning,
    ProvisionEnrollmentInteractor,
)
from apps.admissions.queries import application as app_q
from apps.admissions.queries.provisioning import custom_login_id_taken


def _admission_number(tenant_id) -> str:
    for _ in range(5):
        candidate = f"ADM-{uuid.uuid4().hex[:8].upper()}"
        if not custom_login_id_taken(tenant_id, candidate):
            return candidate
    return f"ADM-{uuid.uuid4().hex[:12].upper()}"


class AdminEnrollFromApplicationView(APIView):
    """POST { confirmDuplicate?, confirmLinked?, batchId? } → provision + enroll."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, application_id) -> Response:
        branch = resolve_branch(request)
        application = app_q.get_application(branch.pk, application_id)
        if application is None:
            return Response({"error": "Application not found."}, status=status.HTTP_404_NOT_FOUND)

        year = get_current_year(branch.pk)
        if year is None:
            return Response({"error": "Set a current academic year before enrolling."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Batch: explicit override, else the first batch of the application's course this year.
        batch = None
        batch_id = request.data.get("batchId")
        batches = list_batches(branch.pk, course_id=application.course_id, academic_year_id=year.id)
        if batch_id:
            batch = next((b for b in batches if str(b.id) == str(batch_id)), None)
        else:
            batch = batches.first() if hasattr(batches, "first") else (batches[0] if batches else None)
        if batch is None:
            return Response(
                {"error": "No batch/section exists for this application's course. Create one first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enq = application.enquiry
        first_name, _, last_name = (enq.applicant_name or "Student").strip().partition(" ")
        profile = application.step.get("applicant", {}) if isinstance(application.step, dict) else {}
        parent_name = profile.get("parentGuardianName") or f"Parent of {first_name}"

        try:
            result = ProvisionEnrollmentInteractor(
                branch=branch, batch=batch, academic_year=year,
                admission_number=_admission_number(branch.tenant_id),
                first_name=first_name, last_name=last_name,
                date_of_birth=enq.date_of_birth, gender=profile.get("gender", ""),
                # The enquiry contact is the parent's; the student gets no own phone/email
                # (avoids a false self-collision in linked-account detection).
                student_phone=None, student_email=None,
                parent_name=parent_name, parent_phone=enq.phone or None,
                parent_email=enq.email or None,
                application=application,
                confirm_linked=bool(request.data.get("confirmLinked")),
                confirm_duplicate=bool(request.data.get("confirmDuplicate")),
                tenant=branch.tenant, user=request.user,
            ).execute()
            return Response(result, status=status.HTTP_201_CREATED)
        except DuplicateStudentError as exc:
            return Response({"duplicate": exc.detail}, status=status.HTTP_409_CONFLICT)
        except LinkedAccountWarning as exc:
            return Response(
                {"parentLinkConfirmationRequired": True, "details": exc.detail},
                status=status.HTTP_409_CONFLICT,
            )
