"""Faculty leave-review queue — student leave requests the faculty can approve/reject.

The review action itself reuses the existing LeaveReviewView
(PATCH /api/v1/attendance/leave/<id>/). This view supplies the read side in the
{ pending, decided } shape the faculty screen expects.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.attendance.queries import leave as leave_q
from apps.attendance.views.student_leave import _leave


class FacultyLeaveReviewView(APIView):
    """GET → { pending, decided } student leave requests for the branch."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        pending, decided = [], []
        for lv in leave_q.list_leaves(branch.pk):
            if not lv.student_id:
                continue
            row = _leave(lv)
            (pending if lv.status == "pending" else decided).append(row)
        return Response({"pending": pending, "decided": decided})
