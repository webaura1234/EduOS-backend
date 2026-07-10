"""Tab-scoped admin admissions GET endpoints for lazy-loaded UI tabs."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import calendar as cal_q
from apps.academics.queries import structure as struct_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.admissions.queries import application as app_q
from apps.admissions.queries import enquiry as enq_q
from apps.admissions.views.admin_overview import (
    _PIPELINE_STAGES,
    _SOURCES,
    _STATUS_TO_STAGE,
    _application,
    _current_cycle_start,
    _enquiry,
)


def _branch_meta(branch, years):
    tenant = branch.tenant
    course_rows = list(struct_q.list_courses(branch.pk))
    return {
        "courses": [c.name for c in course_rows],
        "courseCatalog": [{"id": str(c.id), "name": c.name} for c in course_rows],
        "intakes": [y.name for y in years],
        "institutionName": tenant.name,
        "eligibilityRules": [],
        "notificationLog": [],
    }


def _funnel(enquiries, applications):
    by_stage = {s: 0 for s in _PIPELINE_STAGES}
    by_stage["enquiry"] = len(enquiries)
    enrolled = 0
    for a in applications:
        stage = _STATUS_TO_STAGE.get(a.status, "application")
        by_stage[stage] = by_stage.get(stage, 0) + 1
        if a.status == "enrolled":
            enrolled += 1

    by_source = {s: 0 for s in _SOURCES}
    for e in enquiries:
        by_source[e.source] = by_source.get(e.source, 0) + 1
    for a in applications:
        src = a.enquiry.source if a.enquiry_id else "walk_in"
        by_source[src] = by_source.get(src, 0) + 1

    total_leads = len(enquiries) + len(applications)
    conversion = round(enrolled / total_leads * 100) if total_leads else 0
    return {"byStage": by_stage, "bySource": by_source, "conversionRate": conversion}


def _cycle_context(branch):
    years = list(cal_q.list_years(branch.pk))
    cycle_start = _current_cycle_start(years)
    return years, cycle_start


class AdminAdmissionsOverviewTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        years, cycle_start = _cycle_context(branch)
        enquiries = list(
            enq_q.list_enquiries(branch.pk, created_after=cycle_start, statuses=["new", "contacted"])
        )
        applications = list(app_q.list_applications(branch.pk, created_after=cycle_start))
        return Response({
            **_branch_meta(branch, years),
            "funnel": _funnel(enquiries, applications),
            "notificationLog": [],
        })


class AdminAdmissionsEnquiriesTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        years, cycle_start = _cycle_context(branch)
        enquiries = list(
            enq_q.list_enquiries(branch.pk, created_after=cycle_start, statuses=["new", "contacted"])
        )
        return Response({
            **_branch_meta(branch, years),
            "enquiries": [_enquiry(e) for e in enquiries],
        })


class AdminAdmissionsPipelineTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        years, cycle_start = _cycle_context(branch)
        enquiries = list(
            enq_q.list_enquiries(branch.pk, created_after=cycle_start, statuses=["new", "contacted"])
        )
        applications = list(app_q.list_applications(branch.pk, created_after=cycle_start))
        return Response({
            **_branch_meta(branch, years),
            "enquiries": [_enquiry(e) for e in enquiries],
            "applications": [_application(a) for a in applications],
            "funnel": _funnel(enquiries, applications),
        })


class AdminAdmissionsNotificationsTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        years, cycle_start = _cycle_context(branch)
        applications = list(app_q.list_applications(branch.pk, created_after=cycle_start))
        return Response({
            "institutionName": branch.tenant.name,
            "notificationLog": [],
            "applications": [_application(a) for a in applications],
        })


class AdminAdmissionsWaitlistTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        years, cycle_start = _cycle_context(branch)
        applications = list(app_q.list_applications(branch.pk, created_after=cycle_start))
        waitlisted = [
            _application(a) for a in applications
            if getattr(a, "waitlist_entry", None) is not None
        ]
        return Response({
            **_branch_meta(branch, years),
            "applications": waitlisted,
        })
