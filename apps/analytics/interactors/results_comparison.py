"""Super-admin exam results comparison (F-039) — aggregate-only, no student rows."""

from django.utils import timezone

from apps.examinations.interactors import result as result_i
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import result as result_q
from apps.organizations.queries.branch import get_branch, list_branches


def _breakdown_to_dist(breakdown: list[dict]) -> dict:
    by_band = {row["band"]: row["count"] for row in breakdown}
    return {
        "distinction": by_band.get("90–100", 0),
        "firstClass": by_band.get("75–89", 0),
        "secondClass": by_band.get("60–74", 0) + by_band.get("35–59", 0),
        "fail": by_band.get("<35", 0) + by_band.get("AB", 0),
    }


def _branch_exam_metrics(branch, exam, *, tenant) -> dict | None:
    pub = result_q.get_current_publication(exam.pk)
    if not pub:
        return None
    results = list(result_q.list_student_results(exam.pk))
    if not results:
        return None

    analytics = result_i.get_exam_analytics(exam, tenant=tenant)
    breakdown = analytics.get("breakdown") or []
    dist = _breakdown_to_dist(breakdown)
    appeared = len(results)
    passed = sum(1 for row in results if row.is_pass)
    top_score = max((float(row.percentage) for row in results), default=0.0)

    return {
        "branchId": str(branch.pk),
        "branchName": branch.name,
        "examLabel": exam.name,
        "passPercent": analytics.get("passPercent", 0),
        "appeared": appeared,
        "passed": passed,
        "avgScorePercent": round(float(analytics.get("averagePercent", 0))),
        "topScorePercent": round(top_score),
        "dist": dist,
        "updatedAt": pub.published_at.isoformat(),
        "_breakdown": breakdown,
    }


def _published_exams_for_branch(branch_id) -> list[tuple]:
    """Return (exam, published_at) pairs newest first."""
    rows = []
    for exam in exam_q.list_exams(branch_id):
        pub = result_q.get_current_publication(exam.pk)
        if not pub:
            continue
        if not result_q.list_student_results(exam.pk).exists():
            continue
        rows.append((exam, pub.published_at))
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows


def super_admin_results_comparison(tenant, *, branch_id=None, exam_id=None) -> dict:
    """Cross-branch published exam metrics for the super-admin Results comparison tab."""
    branches = [b for b in list(list_branches(tenant.pk)) if b.is_active]

    exam_options: list[dict] = []
    published_by_branch: dict[str, list[tuple]] = {}
    for branch in branches:
        published = _published_exams_for_branch(branch.pk)
        published_by_branch[str(branch.pk)] = published
        for exam, _pub_at in published:
            exam_options.append({
                "examId": str(exam.pk),
                "examLabel": exam.name,
                "branchId": str(branch.pk),
                "branchName": branch.name,
            })

    branch_options = [{"branchId": str(b.pk), "branchName": b.name} for b in branches]

    selected_branch_id = str(branch_id) if branch_id else None
    selected_exam_id = str(exam_id) if exam_id else None

    metric_rows: list[dict] = []

    if selected_exam_id:
        for branch in branches:
            exam = exam_q.get_exam(branch.pk, selected_exam_id)
            if not exam:
                continue
            row = _branch_exam_metrics(branch, exam, tenant=tenant)
            if row:
                metric_rows.append(row)
                break
    elif selected_branch_id:
        branch = get_branch(tenant.pk, selected_branch_id)
        if branch and branch.is_active:
            published = published_by_branch.get(str(branch.pk), [])
            if published:
                exam = published[0][0]
                row = _branch_exam_metrics(branch, exam, tenant=tenant)
                if row:
                    metric_rows.append(row)
    else:
        for branch in branches:
            published = published_by_branch.get(str(branch.pk), [])
            if not published:
                continue
            exam = published[0][0]
            row = _branch_exam_metrics(branch, exam, tenant=tenant)
            if row:
                metric_rows.append(row)

    score_band_totals: dict[str, int] = {}
    for row in metric_rows:
        for band_row in row.pop("_breakdown", []):
            label = band_row["band"]
            score_band_totals[label] = score_band_totals.get(label, 0) + band_row["count"]

    band_order = ["90–100", "75–89", "60–74", "35–59", "<35", "AB"]
    score_bands = [
        {"band": label, "count": score_band_totals.get(label, 0)}
        for label in band_order
        if score_band_totals.get(label, 0) > 0 or label in score_band_totals
    ]
    score_bands = [b for b in score_bands if b["count"] > 0]

    return {
        "branches": metric_rows,
        "scoreBands": score_bands,
        "filterOptions": {
            "branches": branch_options,
            "exams": exam_options,
        },
        "selectedBranchId": selected_branch_id,
        "selectedExamId": selected_exam_id,
        "generatedAt": timezone.now().isoformat(),
    }
