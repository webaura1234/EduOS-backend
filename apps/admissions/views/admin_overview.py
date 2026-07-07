"""Admin Admissions overview — the AdmissionsData aggregate the admin screen consumes.

Real data for enquiries, applications, funnel, courses, intakes, institution name.
notificationLog and eligibilityRules are not yet modelled → returned empty.
"""

import datetime

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import calendar as cal_q
from apps.academics.queries import structure as struct_q
from apps.admissions.queries import application as app_q
from apps.admissions.queries import enquiry as enq_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin


def _current_cycle_start(years: list) -> datetime.datetime | None:
    """Start of the current admission cycle's rolling window: one year before
    the current academic year begins, so applicants who apply ahead of the
    year's start date still show on the live pipeline. Falls back to the most
    recent academic year if none is explicitly marked current; returns None
    (no scoping) if the branch has no academic year configured yet."""
    if not years:
        return None
    current_year = next((y for y in years if y.is_current), years[0])
    return datetime.datetime.combine(
        current_year.start_date - datetime.timedelta(days=365),
        datetime.time.min, tzinfo=datetime.timezone.utc,
    )

# Backend ApplicationStatus → frontend PipelineStage.
# "submitted" means "wizard started / in progress", not "documents collected",
# so it belongs in the application column, not documents.
# The documents column will be populated once document upload (S3) is built
# and we introduce a dedicated status for that phase.
_STATUS_TO_STAGE = {
    "draft": "application",
    "submitted": "application",
    "under_review": "documents",
    "accepted": "verification",
    "waitlisted": "application",
    "enrolled": "enrollment",
    "rejected": "application",
}
_PIPELINE_STAGES = ["enquiry", "application", "documents", "verification", "enrollment"]
_SOURCES = ["walk_in", "social", "referral", "online"]
_DOC_STATUS = {"pending": "pending", "verified": "verified", "rejected": "rejected"}


def _enquiry(e) -> dict:
    return {
        "id": str(e.id),
        "applicantName": e.applicant_name,
        "phone": e.phone,
        "email": e.email,
        "source": e.source,
        "courseInterest": e.course.name if e.course_id else "",
        "notes": e.notes,
        "createdAt": e.created_at.isoformat(),
    }


def _active_documents(a):
    # Uses the prefetched `active_documents` (to_attr) when available; falls back otherwise.
    prefetched = getattr(a, "active_documents", None)
    return prefetched if prefetched is not None else a.documents.filter(is_active=True)


def _document(d) -> dict:
    return {
        "id": str(d.id),
        "name": d.doc_type,
        "status": _DOC_STATUS.get(d.verification_status, "pending"),
        "uploadedAt": d.created_at.isoformat(),
        "storageKey": d.s3_key,
    }


def _wizard(step: dict) -> dict:
    step = step or {}
    return {
        "currentStep": step.get("currentStep", step.get("step", 0)) or 0,
        "completedSteps": step.get("completedSteps", []),
        "lastSavedAt": step.get("lastSavedAt", ""),
    }


def _eligibility(result):
    if isinstance(result, dict) and "eligible" in result:
        return {"eligible": result.get("eligible", False), "rules": result.get("rules", [])}
    return None


def _applicant_profile(a, enq) -> dict:
    step = a.step if isinstance(a.step, dict) else {}
    profile = step.get("applicant", {}) if isinstance(step.get("applicant"), dict) else {}
    dob = profile.get("dateOfBirth") or (
        enq.date_of_birth.isoformat() if enq.date_of_birth else ""
    )
    return {
        "dateOfBirth": dob,
        "gender": profile.get("gender", ""),
        "previousSchool": profile.get("previousSchool", ""),
        "previousGrade": profile.get("previousGrade", ""),
        "previousMarksPercent": profile.get("previousMarksPercent"),
        "parentGuardianName": profile.get("parentGuardianName", ""),
        "address": profile.get("address", ""),
    }


def _application(a) -> dict:
    enq = a.enquiry
    is_rejected = a.status == "rejected"
    waitlist = getattr(a, "waitlist_entry", None)
    enrollments = getattr(a, "active_enrollments", None) or []
    enrolled_profile_id = (
        str(enrollments[0].student_profile_id) if enrollments else None
    )
    profile = _applicant_profile(a, enq)
    return {
        "id": str(a.id),
        "applicantName": enq.applicant_name,
        "phone": enq.phone,
        "email": enq.email,
        "course": a.course.name if a.course_id else "",
        "intake": "",
        "stage": _STATUS_TO_STAGE.get(a.status, "application"),
        "source": enq.source,
        "wizard": _wizard(a.step),
        "applicant": profile,
        "eligibility": _eligibility(a.eligibility_result),
        "documents": [_document(d) for d in _active_documents(a)],
        "meritScore": None,
        "waitlisted": waitlist is not None,
        "waitlistRank": waitlist.rank if waitlist else None,
        "waitlistEntryId": str(waitlist.id) if waitlist else None,
        "parentPhone": enq.phone or None,
        "parentLinkedWarning": False,
        "status": "rejected" if is_rejected else "active",
        "rejection": (
            {"reason": a.rejection_reason, "rejectedAt": a.updated_at.isoformat()}
            if is_rejected else None
        ),
        "feeSnapshot": None,
        "provisioning": None,
        "archivedBranchLink": None,
        "enrolledStudentId": enrolled_profile_id,
        "photoS3Key": None,
        "photoUrl": None,
        "idCardGeneratedAt": None,
        "createdAt": a.created_at.isoformat(),
        "updatedAt": a.updated_at.isoformat(),
    }


class AdminAdmissionsOverviewView(APIView):
    """GET → AdmissionsData (full admissions aggregate for the admin screen).

    ``enquiries``/``applications`` here feed the live Kanban pipeline, which
    needs its whole working set in one shot (a board can't page). Since neither
    model has an explicit admission-cycle field, both are scoped to a rolling
    window starting a year before the current academic year begins (covering
    early applicants) instead of every enquiry/application ever filed — a
    school running for years would otherwise load its entire admissions
    history into one board.
    """
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        tenant = branch.tenant

        years = list(cal_q.list_years(branch.pk))
        cycle_start = _current_cycle_start(years)
        enquiries = list(enq_q.list_enquiries(branch.pk, created_after=cycle_start))
        applications = list(app_q.list_applications(branch.pk, created_after=cycle_start))

        # Funnel — counts per pipeline stage + per enquiry source.
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

        conversion = round(enrolled / len(enquiries) * 100) if enquiries else 0

        courses = [c.name for c in struct_q.list_courses(branch.pk)]
        course_rows = list(struct_q.list_courses(branch.pk))
        intakes = [y.name for y in years]

        return Response({
            "enquiries": [_enquiry(e) for e in enquiries],
            "applications": [_application(a) for a in applications],
            "funnel": {
                "byStage": by_stage,
                "bySource": by_source,
                "conversionRate": conversion,
            },
            "courses": courses,
            "courseCatalog": [{"id": str(c.id), "name": c.name} for c in course_rows],
            "intakes": intakes,
            "institutionName": tenant.name,
            # Not yet modelled — empty so the screen renders; build per priority.
            "notificationLog": [],
            "eligibilityRules": [],
        })
