"""Student-facing leave — the logged-in student's own leave requests + self-apply."""

import datetime

from rest_framework import status as http
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsStudent
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.attendance.interactors import leave as leave_i
from apps.attendance.queries import leave as leave_q


def _leave(lv) -> dict:
    student = lv.student
    has_batch = student and student.current_batch_id
    return {
        "id": str(lv.id),
        "studentId": str(student.student_profile_id) if student else "",
        "studentName": student.user.full_name if student else "",
        "classSectionId": str(student.current_batch_id) if has_batch else "",
        "classLabel": student.current_batch.name if has_batch else "",
        "fromDate": lv.from_date.isoformat(),
        "toDate": lv.to_date.isoformat(),
        "reason": lv.reason,
        "status": lv.status if lv.status in ("pending", "approved", "rejected") else "pending",
        "appliedByRole": "parent" if lv.applicant_role == "parent" else "student",
        "appliedByName": lv.applied_by.full_name if lv.applied_by_id else "",
        "appliedAt": lv.created_at.isoformat(),
        "reviewedByUserId": str(lv.approver_id) if lv.approver_id else None,
        "reviewedByName": lv.approver.full_name if lv.approver_id else None,
        "reviewedAt": lv.approved_at.isoformat() if lv.approved_at else None,
        "reviewNote": lv.decision_note or None,
    }


def _enrollment(request, branch):
    profile = getattr(request.user, "student_profile", None)
    if not profile:
        return None
    return get_active_enrollment_for_profile(profile.pk)


class StudentLeaveView(APIView):
    """GET → { requests }; POST { fromDate, toDate, reason } → apply leave."""
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        enrollment = _enrollment(request, branch)
        if enrollment is None:
            return Response({"requests": []})
        leaves = leave_q.list_leaves(branch.pk, student_id=enrollment.pk)
        return Response({"requests": [_leave(lv) for lv in leaves]})

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        profile = getattr(request.user, "student_profile", None)
        if profile is None:
            return Response({"error": "Student profile not found."}, status=http.HTTP_400_BAD_REQUEST)

        try:
            from_date = datetime.date.fromisoformat(request.data.get("fromDate"))
            to_date = datetime.date.fromisoformat(request.data.get("toDate"))
        except (TypeError, ValueError):
            raise ValidationError({"fromDate": "Valid fromDate and toDate are required."})

        # apply_student_leave's shim resolves the StudentProfile id → enrollment.
        leave = leave_i.apply_student_leave(
            branch=branch, student_id=profile.pk,
            from_date=from_date, to_date=to_date,
            reason=request.data.get("reason", ""),
            applied_by=request.user,
        )
        return Response({"leave": _leave(leave)}, status=http.HTTP_201_CREATED)
