"""Tab-scoped admin examinations GET endpoints."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.examinations.permissions import IsAdminOrSuperAdmin
from apps.examinations.views.admin_overview import (
    AdminExaminationsOverviewView,
    _current_academic_year_id,
    _result_status,
    _seating_plan,
)
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import invigilator as inv_q
from apps.examinations.queries import registration as reg_q
from apps.examinations.queries import result as result_q
from apps.examinations.queries import seating as seat_q
from apps.examinations.serializers.exam import ExamScheduleSlotSerializer
from apps.examinations.serializers.registration import ExamRegistrationSerializer


def _exam_bundle(branch):
    year_id = _current_academic_year_id(branch.pk)
    exams = list(exam_q.list_exams_for_year(branch.pk, academic_year_id=year_id))
    exam_ids = [e.id for e in exams]
    slots = list(exam_q.list_schedule_slots_for_exams(exam_ids))
    registrations = list(reg_q.list_registrations_for_exams(exam_ids))
    duties = list(inv_q.list_duties_for_exams(exam_ids))
    seatings = list(seat_q.list_seatings_for_exams(exam_ids))
    publications = list(result_q.list_publications_for_exams(exam_ids))
    notes_by_publication = result_q.latest_notes_for_publications([p.id for p in publications])

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

    exam_rows = [
        {
            "id": str(e.id),
            "name": e.name,
            "examType": e.exam_type,
            "isPublished": e.is_published,
            "resultStatus": e.result_status,
        }
        for e in exams
    ]
    slot_rows = ExamScheduleSlotSerializer(slots, many=True).data

    return {
        "institutionType": branch.tenant.institution_type,
        "exams": exam_rows,
        "slots": slot_rows,
        "students": students,
        "seatingPlans": seating_plans,
        "invigilation": invigilation,
        "faculty": inv_q.faculty_options_for_branch(branch.tenant_id, branch.pk),
        "resultStatusByExam": result_status_by_exam,
        "publishedResults": published_results,
    }


class AdminExaminationsScheduleTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        b = _exam_bundle(branch)
        return Response({
            "institutionType": b["institutionType"],
            "exams": b["exams"],
            "slots": b["slots"],
            "students": b["students"],
        })


class AdminExaminationsSeatingTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        b = _exam_bundle(branch)
        return Response({
            "institutionType": b["institutionType"],
            "slots": b["slots"],
            "students": b["students"],
            "seatingPlans": b["seatingPlans"],
        })


class AdminExaminationsInvigilationTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        b = _exam_bundle(branch)
        return Response({
            "institutionType": b["institutionType"],
            "slots": b["slots"],
            "invigilation": b["invigilation"],
            # Active faculty only — assignment UI must not invent its own roster.
            "faculty": b["faculty"],
        })


class AdminExaminationsResultsTabView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        b = _exam_bundle(branch)
        return Response({
            "institutionType": b["institutionType"],
            "slots": b["slots"],
            "resultStatusByExam": b["resultStatusByExam"],
            "publishedResults": b["publishedResults"],
        })

