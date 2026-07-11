# Adding a new ERP report

Reports are tabular CSV exports. Documents (receipts, hall tickets, report cards) use the separate PDF pipeline — do not register them here.

## Checklist

1. Add a `ReportType` value in [`apps/analytics/enums.py`](../../analytics/enums.py).
2. Choose a base class in [`apps/core/exports/base.py`](base.py):
   - **Queryset** — one ORM row per CSV row (`ExportDefinition`).
   - **Aggregation** — pivot/summary rows (`AggregationExportDefinition` + `resolve_rows`).
3. Implement the class in the module's `exports.py` with metadata:
   - `module`, `description`, `allowed_roles`, `filters`, `supports_preview`, `estimated_runtime`.
4. Register via `register()` in `register_all()`; ensure `AppConfig.ready()` imports the module.
5. Add parity tests (column order, row count, permissions).
6. Verify output against [Migration Verification](../../../../../.cursor/plans/unified_reporting_framework_7cdbcf73.plan.md) criteria before merging.

## Deferred: NAAC/NIRF CSV exports

NAAC/NIRF export endpoints are not implemented in the current backend (`/api/v1/admin/college/naac/export/` and `/nirf/export/` do not exist). Registration in the unified reporting framework is deferred until the backend export functionality exists.

The analytics gaps endpoint (`GET /api/v1/analytics/reports/naac/`) remains available for gap review only. Do not register placeholder `ExportDefinition` classes or expose non-functional reports in the catalog.

## Future modules (library, transport, inventory)

When a module ships its first report, create `apps/{module}/exports.py` following the fees/attendance pattern. No empty app scaffolding is required until then.

## APIs

- Catalog: `GET /api/v1/analytics/reports/catalog/`
- Export: `POST /api/v1/analytics/reports/` (existing)
- Preview: `POST /api/v1/analytics/reports/preview/` (when `supports_preview=True`)
- Saved filters: `GET/POST /api/v1/analytics/reports/saved-filters/`
