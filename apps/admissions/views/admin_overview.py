"""Admin Admissions overview — the AdmissionsData aggregate the admin screen consumes.

Real data for enquiries, applications, funnel, courses, intakes, institution name.
notificationLog and eligibilityRules are not yet modelled → returned empty.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import calendar as cal_q
from apps.academics.queries import structure as struct_q
from apps.admissions.queries import application as app_q
from apps.admissions.queries import enquiry as enq_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin

# Backend ApplicationStatus → frontend PipelineStage.
_STATUS_TO_STAGE = {
    "draft": "application",
    "submitted": "documents",
    "under_review": "verification",
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


def _application(a) -> dict:
    enq = a.enquiry
    is_rejected = a.status == "rejected"
    waitlist = getattr(a, "waitlist_entry", None)
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
        "applicant": {
            "dateOfBirth": enq.date_of_birth.isoformat() if enq.date_of_birth else "",
            "gender": "",
            "previousSchool": "",
            "previousGrade": "",
            "previousMarksPercent": None,
            "parentGuardianName": "",
            "address": "",
        },
        "eligibility": _eligibility(a.eligibility_result),
        "documents": [_document(d) for d in _active_documents(a)],
        "meritScore": None,
        "waitlisted": waitlist is not None,
        "waitlistRank": waitlist.rank if waitlist else None,
        "parentPhone": None,
        "parentLinkedWarning": False,
        "status": "rejected" if is_rejected else "active",
        "rejection": (
            {"reason": a.rejection_reason, "rejectedAt": a.updated_at.isoformat()}
            if is_rejected else None
        ),
        "feeSnapshot": None,
        "provisioning": None,
        "archivedBranchLink": None,
        "enrolledStudentId": None,
        "photoS3Key": None,
        "photoUrl": None,
        "idCardGeneratedAt": None,
        "createdAt": a.created_at.isoformat(),
        "updatedAt": a.updated_at.isoformat(),
    }


class AdminAdmissionsOverviewView(APIView):
    """GET → AdmissionsData (full admissions aggregate for the admin screen)."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        tenant = branch.tenant

        enquiries = list(enq_q.list_enquiries(branch.pk))
        applications = list(app_q.list_applications(branch.pk))

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
        intakes = [y.name for y in cal_q.list_years(branch.pk)]

        return Response({
            "enquiries": [_enquiry(e) for e in enquiries],
            "applications": [_application(a) for a in applications],
            "funnel": {
                "byStage": by_stage,
                "bySource": by_source,
                "conversionRate": conversion,
            },
            "courses": courses,
            "intakes": intakes,
            "institutionName": tenant.name,
            # Not yet modelled — empty so the screen renders; build per priority.
            "notificationLog": [],
            "eligibilityRules": [],
        })
