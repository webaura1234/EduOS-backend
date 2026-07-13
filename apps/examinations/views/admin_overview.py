"""Admin Examinations overview — the ExaminationsData aggregate the admin screen
consumes for exams, slots, registrations, seating, invigilation, and results.

Replaces a Next.js BFF orchestration that looped over every exam and, per exam,
sequentially fetched schedule/slots, then one more call per distinct
class-section for student registrations, then results-status, then
invigilators, then seating — an N×M chain of sequential Django round trips
(see fetchExaminationsFromDjango, since removed from examinations-server.ts).
Everything here is instead ~6 batched queries across all of a branch's exams.

Exams are also scoped to the current academic year (falling back to the most
recent one, or unscoped if none is configured) — the branch's exam history
otherwise grows without bound across every year the school has run, and nothing
downstream (a Kanban-style overview, not a paginated table) can page through it.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import AcademicYear
from apps.academics.scoping import resolve_branch
from apps.examinations.permissions import IsAdminOrSuperAdmin
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import invigilator as inv_q
from apps.examinations.queries import registration as reg_q
from apps.examinations.queries import result as result_q
from apps.examinations.queries import seating as seat_q
from apps.examinations.serializers.exam import ExamScheduleSlotSerializer
from apps.examinations.serializers.registration import ExamRegistrationSerializer


def _branch_years(branch_id) -> list:
    """The branch's academic years, newest first (reused for scoping + the picker)."""
    return list(
        AcademicYear.objects.filter(branch_id=branch_id, is_active=True).order_by("-start_date")
    )


def _default_year_id(years: list):
    """Current year id, falling back to the most recent; None if none configured."""
    if not years:
        return None
    current = next((y for y in years if y.is_current), years[0])
    return current.id


def _resolve_year_id(years: list, requested_id):
    """Use the requested academic year only if it belongs to the branch; otherwise
    fall back to the current year. Prevents cross-branch id probing and lets the
    admin view a prior year's exams/results without changing the default (audit P1.2)."""
    if requested_id:
        for y in years:
            if str(y.id) == str(requested_id):
                return y.id
    return _default_year_id(years)


def _current_academic_year_id(branch_id):
    """The branch's current academic year id, falling back to the most recent
    one if none is explicitly marked current; None (no scoping) if the branch
    has no academic year configured yet. Retained for other importers
    (e.g. admin_tab_overview)."""
    return _default_year_id(_branch_years(branch_id))


def _result_status(exam) -> str:
    """Mirrors the frontend's mapExamResultStatus exactly."""
    if exam.is_published:
        return "revised" if exam.result_status == "revised" else "published"
    if exam.result_status == "provisional":
        return "provisional"
    return "draft"


def _seating_plan(slot_id, seatings: list) -> dict | None:
    if not seatings:
        return None
    by_room: dict = {}
    for s in seatings:
        room_id = str(s.room_id)
        bucket = by_room.setdefault(room_id, {"roomId": room_id, "roomName": s.room.name, "seats": []})
        bucket["seats"].append({
            "studentId": str(s.student.student_profile_id),
            "enrollmentId": str(s.student_id),
            "studentName": s.student.user.full_name,
            "seatNo": int(s.seat_number) if str(s.seat_number).isdigit() else s.seat_number,
        })
    allocations = list(by_room.values())
    for allocation in allocations:
        allocation["seats"].sort(
            key=lambda seat: int(seat["seatNo"]) if str(seat["seatNo"]).isdigit() else str(seat["seatNo"])
        )
    generated_at = max(s.created_at for s in seatings).isoformat()
    return {
        "examSlotId": str(slot_id),
        "generatedAt": generated_at,
        "totalStudents": len(seatings),
        "allocations": allocations,
        "note": "Loaded from saved seating.",
    }


class AdminExaminationsOverviewView(APIView):
    """GET → ExaminationsData (exams/slots/students/seating/invigilation/results
    for the admin screen; batched, scoped to the current academic year)."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)

        years = _branch_years(branch.pk)
        year_id = _resolve_year_id(years, request.query_params.get("academicYearId"))
        exams = list(exam_q.list_exams_for_year(branch.pk, academic_year_id=year_id))
        exam_ids = [e.id for e in exams]

        slots = list(exam_q.list_schedule_slots_for_exams(exam_ids))
        registrations = list(reg_q.list_registrations_for_exams(exam_ids))
        duties = list(inv_q.list_duties_for_exams(exam_ids))
        seatings = list(seat_q.list_seatings_for_exams(exam_ids))
        publications = list(result_q.list_publications_for_exams(exam_ids))
        notes_by_publication = result_q.latest_notes_for_publications([p.id for p in publications])

        # Students registered for any exam — de-duped by studentId, matching
        # the old per-(exam, class-section) fetch-and-merge loop.
        students = []
        seen_students: set = set()
        for reg in ExamRegistrationSerializer(registrations, many=True).data:
            sid = reg["studentId"]
            if sid in seen_students:
                continue
            seen_students.add(sid)
            students.append({
                "studentId": sid,
                "name": reg["studentName"],
                "classSectionId": reg["classSectionId"],
                "classLabel": reg["classLabel"],
                "examFeePaid": reg["feePaid"],
            })

        # Seating plans — group seatings by slot, one plan per slot with seatings.
        seatings_by_slot: dict = {}
        for s in seatings:
            seatings_by_slot.setdefault(s.schedule_slot_id, []).append(s)
        seating_plans = [
            plan for slot_id, slot_seatings in seatings_by_slot.items()
            if (plan := _seating_plan(slot_id, slot_seatings)) is not None
        ]

        invigilation = [
            {
                "examSlotId": str(d.schedule_slot_id),
                "facultyId": str(d.faculty_id),
                "facultyName": d.faculty.full_name,
                "assignedAt": d.created_at.isoformat(),
                "assignedBy": "manual",
            }
            for d in duties
        ]

        # Result status + published results are broadcast per SLOT (matching the
        # old per-exam loop, which tagged every slot of an exam with that exam's
        # status/publications).
        slot_ids_by_exam: dict = {}
        for s in slots:
            slot_ids_by_exam.setdefault(s.exam_id, []).append(s.id)

        result_status_by_exam: dict = {}
        for exam in exams:
            status = _result_status(exam)
            for slot_id in slot_ids_by_exam.get(exam.id, []):
                result_status_by_exam[str(slot_id)] = status

        publications_by_exam: dict = {}
        for pub in publications:
            publications_by_exam.setdefault(pub.exam_id, []).append(pub)

        published_results = []
        for exam in exams:
            for pub in publications_by_exam.get(exam.id, []):
                note = notes_by_publication.get(pub.id) or (
                    "Published" if pub.revision_no == 1 else "Revised"
                )
                for slot_id in slot_ids_by_exam.get(exam.id, []):
                    published_results.append({
                        "id": str(pub.id),
                        "examSlotId": str(slot_id),
                        "publishedAt": pub.published_at.isoformat(),
                        "publishedByUserId": str(pub.published_by_id) if pub.published_by_id else "",
                        "revisionNo": pub.revision_no,
                        "note": note,
                        "entries": [],
                    })

        return Response({
            "institutionType": branch.tenant.institution_type,
            "exams": [
                {
                    "id": str(e.id),
                    "name": e.name,
                    "examType": e.exam_type,
                    "isPublished": e.is_published,
                    "resultStatus": e.result_status,
                }
                for e in exams
            ],
            "slots": ExamScheduleSlotSerializer(slots, many=True).data,
            "students": students,
            "seatingPlans": seating_plans,
            "invigilation": invigilation,
            # Active faculty only — same source as auto-assign / duty writes.
            "faculty": inv_q.faculty_options_for_branch(branch.tenant_id, branch.pk),
            "resultStatusByExam": result_status_by_exam,
            "publishedResults": published_results,
            # Academic-year picker: lets the admin view a prior year's exams and
            # results after a rollover (audit P1.2). Omitting the param keeps the
            # current-year default unchanged.
            "academicYears": [
                {"id": str(y.id), "name": y.name, "isCurrent": y.is_current}
                for y in years
            ],
            "selectedAcademicYearId": str(year_id) if year_id else None,
        })
