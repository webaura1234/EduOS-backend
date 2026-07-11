"""Optional paginated preview for reports with supports_preview=True."""

from apps.core.exports.base import AggregationExportDefinition, ExportDefinition


def preview_export(
    definition: ExportDefinition,
    *,
    tenant,
    branch,
    params: dict,
    page: int = 1,
    page_size: int = 50,
    search: str = "",
    sort_key: str = "",
    sort_dir: str = "asc",
) -> dict:
    if not definition.supports_preview:
        raise ValueError(f"Report {definition.report_type!r} does not support preview.")

    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    columns = definition.get_columns(params)
    col_keys = [c.key for c in columns]

    if isinstance(definition, AggregationExportDefinition):
        rows = definition.resolve_rows(
            tenant=tenant, branch=branch, params=params,
        )
    else:
        qs = definition.get_queryset_for_export(
            tenant_id=tenant.pk,
            branch_id=branch.pk if branch else None,
            params=params,
        )
        rows = [definition.get_row(obj) for obj in qs.iterator(chunk_size=500)]

    if search:
        needle = search.lower()
        rows = [
            r for r in rows
            if any(needle in str(r.get(k, "")).lower() for k in col_keys)
        ]

    if sort_key and sort_key in col_keys:
        reverse = sort_dir.lower() == "desc"
        rows.sort(key=lambda r: (r.get(sort_key) is None, r.get(sort_key)), reverse=reverse)

    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]

    return {
        "columns": [{"key": c.key, "label": c.label, "format": c.format} for c in columns],
        "rows": page_rows,
        "total": total,
        "page": page,
        "pageSize": page_size,
    }
