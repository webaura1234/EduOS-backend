"""Super-admin cross-branch academic-year overview (F-036)."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from apps.academics.queries.calendar import list_years
from apps.accounts.permissions import IsSuperAdmin
from apps.organizations.queries.branch import list_branches


class AcademicYearOverviewView(APIView):
    """GET → every branch's academic years with progress status (super-admin)."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request) -> Response:
        today = timezone.localdate()
        rows = []
        for branch in list_branches(request.user.tenant_id):
            for year in list_years(branch.id):
                start, end = year.start_date, year.end_date
                span = (end - start).days or 1
                if today < start:
                    status, days_remaining, percent = "upcoming", None, 0
                elif today > end:
                    status, days_remaining, percent = "ended", None, 100
                else:
                    status = "in_progress"
                    days_remaining = (end - today).days
                    percent = round((today - start).days / span * 100)
                rows.append({
                    "branchId": str(branch.id),
                    "branchName": branch.name,
                    "academicYearLabel": year.name,
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "status": status,
                    "daysRemaining": days_remaining,
                    "percentElapsed": percent,
                })
        return Response({"rows": rows, "generatedAt": timezone.now().isoformat()})
