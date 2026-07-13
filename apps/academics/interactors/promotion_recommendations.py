"""Read-only promotion recommendation engine (mirrors rollover logic without importing rollover)."""

from __future__ import annotations

from dataclasses import dataclass

from apps.academics.helpers import is_college, is_school
from apps.academics.queries import structure as struct_q
from apps.admissions.queries import enrollment as enr_q
from apps.examinations.models import ExamRegistration
from apps.examinations.queries import marks as exam_marks_q

from apps.academics.models.promotion import PromotionAction

PROMOTION_REASON_LABELS: dict[str, str] = {
    "results_not_published": "Exam results are not yet published",
    "missing_batch": "No class assigned",
    "missing_enrollment": "Enrollment record is missing",
    "next_course_available": "",
    "no_yearly_pass_fail_policy": "Student requires manual review",
    "college_arrears_pending": "",
    "final_year_clear": "",
    "final_year": "",
    "course_sequence_gap": "Course progression could not be determined",
}


def reason_label(code: str) -> str:
    return PROMOTION_REASON_LABELS.get(code, "")


@dataclass
class PromotionRecommendation:
    action: str
    reason_code: str = ""
    reason_label: str = ""


def _get_next_course(department_id, current_course_id):
    courses = list(struct_q.list_courses_in_department_ordered(department_id))
    ids = [c.pk for c in courses]
    if current_course_id not in ids:
        return None
    idx = ids.index(current_course_id)
    if idx + 1 < len(courses):
        return courses[idx + 1]
    return None


def get_next_course(department_id, current_course_id):
    """Public helper for preparation mapping (mirrors rollover read logic)."""
    return _get_next_course(department_id, current_course_id)


def _has_unpublished_exam_results(enrollment_id, academic_year_id) -> bool:
    """True when the student is registered for exams in the year that are not yet published."""
    return ExamRegistration.objects.filter(
        student_id=enrollment_id,
        is_active=True,
        exam__is_active=True,
        exam__is_published=False,
        exam__academic_period__academic_year_id=academic_year_id,
    ).exists()


def recommend_for_student(*, profile, tenant, source_year_id, enrollment=None) -> PromotionRecommendation:
    enrollment = enrollment or enr_q.get_active_enrollment_for_profile(
        profile.pk, academic_year_id=source_year_id
    )
    batch = enrollment.batch if enrollment else profile.current_batch
    if not batch:
        code = "missing_batch"
        return PromotionRecommendation(
            action=PromotionAction.PENDING,
            reason_code=code,
            reason_label=reason_label(code),
        )

    if enrollment and _has_unpublished_exam_results(enrollment.pk, source_year_id):
        code = "results_not_published"
        return PromotionRecommendation(
            action=PromotionAction.PENDING,
            reason_code=code,
            reason_label=reason_label(code),
        )

    courses = list(struct_q.list_courses_in_department_ordered(batch.course.department_id))
    course_ids = [c.pk for c in courses]
    if batch.course_id not in course_ids:
        code = "course_sequence_gap"
        return PromotionRecommendation(
            action=PromotionAction.MANUAL_REVIEW,
            reason_code=code,
            reason_label=reason_label(code),
        )

    next_course = _get_next_course(batch.course.department_id, batch.course_id)

    if next_course is not None:
        if is_college(tenant):
            code = "next_course_available"
            return PromotionRecommendation(
                action=PromotionAction.PROMOTE,
                reason_code=code,
                reason_label=reason_label(code),
            )
        if is_school(tenant):
            code = "no_yearly_pass_fail_policy"
            return PromotionRecommendation(
                action=PromotionAction.MANUAL_REVIEW,
                reason_code=code,
                reason_label=reason_label(code),
            )
        code = "no_yearly_pass_fail_policy"
        return PromotionRecommendation(
            action=PromotionAction.MANUAL_REVIEW,
            reason_code=code,
            reason_label=reason_label(code),
        )

    # Final year
    if is_college(tenant):
        if not enrollment:
            code = "missing_enrollment"
            return PromotionRecommendation(
                action=PromotionAction.PENDING,
                reason_code=code,
                reason_label=reason_label(code),
            )
        if exam_marks_q.open_arrear_subjects(enrollment.pk):
            code = "college_arrears_pending"
            return PromotionRecommendation(
                action=PromotionAction.RETAIN,
                reason_code=code,
                reason_label=reason_label(code),
            )
        code = "final_year_clear"
        return PromotionRecommendation(
            action=PromotionAction.GRADUATE,
            reason_code=code,
            reason_label=reason_label(code),
        )

    code = "final_year"
    return PromotionRecommendation(
        action=PromotionAction.GRADUATE,
        reason_code=code,
        reason_label=reason_label(code),
    )
