# Stage 9 — Dashboards, Reports & Audit (Analytics): Detailed Implementation Plan

> Same discipline as Stages 1–7: thin views → interactors → queries, **all ORM in
> `queries/`**, camelCase serializers. This module is the **aggregation layer** — it mostly
> READS, composing the other modules through *their query layers* (never their `.objects`),
> plus it owns two genuinely-new write surfaces: the hash-chained **AuditLog** and **report
> exports**. Do this stage last (per the roadmap): it aggregates everything already built.

---

## 0. Current state of the app

`apps/analytics/` is a **registered but empty skeleton** (in `INSTALLED_APPS`,
`api/v1/analytics/`). Tree exists (models `logs`/`data_ops`; interactors `report`/`audit`/
`data_export`; views `report`/`audit`/`job`), all stubs. Greenfield.

Everything it aggregates already exists and exposes query/interactor functions to reuse:
`fees.queries.defaulter` + collection metrics, `attendance.interactors.report`
(shortage/monthly/%), `examinations.interactors.result` analytics, `admissions.queries.enquiry`
funnel, `hr.queries.leave.leave_summary`, plus per-module dashboards. **Analytics must call
these, not re-query their models** (cross-app boundary).

---

## 1. Goal & scope

**Role dashboards (read aggregates):**
1. **Admin dashboard + alerts** (F-051/F-053) — today's present count, fee collected today,
   classes running; alerts for low-attendance, pending fees, upcoming exams.
2. **Faculty / Student / Parent dashboards** (F-181/F-196/F-211) — schedule, attendance %,
   fee/exam/announcement summaries scoped to the caller.
3. **Collection dashboard** (F-138) + **shortage alerts** (F-114).

**Super-admin cross-branch (F-021–F-040):**
4. **Multi-branch consolidated dashboard** (F-021) + **branch comparison** (F-022) +
   **cross-branch analytics drill-down** (F-025) + **consolidated defaulter** (F-038) +
   **exam-results comparison** (F-039).

**Audit & support (F-239/F-240):**
5. **AuditLog** — append-only, **hash-chained** per tenant; a `record_audit()` helper that
   sensitive mutations call; a filtered, read-only audit endpoint.
6. **SupportModeLog** — platform-owner support-session start/end + actions.

**Reports & exports (F-062/F-063/F-064/F-110/F-147/F-236/F-048):**
7. **Module-wise reports** (F-062) with **snapshot-at-request** semantics (F-064/EC-RPT-03).
8. **Export service** — small inline (CSV/JSON), large via background job (F-063/EC-RPT-01)
   with a `ReportExport` job row + signed-URL seam (F-236).
9. **NAAC/NIRF export with gaps** (F-048/F-237) — college; lists missing fields, exports anyway.

**In scope per OD-2:** a real Celery task pipeline + S3 storage layer for report exports
(tested with eager Celery + a `SandboxS3` adapter; live broker/AWS swapped at deploy).

**Out of scope (later Compliance/Operations stage):** DSAR `DataExport`/`DataDeletion`
(EC-PRIV-*), the Celery **beat scheduler** + real Redis broker in CI (tests run eager),
materialized/precomputed aggregate stores (we compute live with a short cache seam, OD-1),
and the nightly hash-chain verifier **daemon** (we implement the chain + an on-demand verify
function, not the cron).

---

## 2. Critical dependencies & decisions

| # | Decision | Resolution |
|---|----------|-----------|
| D1 | **Aggregate by reusing module queries** | Dashboards call `fees`/`attendance`/`examinations`/`admissions`/`hr` **query + interactor** functions and compose results. Analytics adds **no** cross-app `.objects`. New aggregate reads it genuinely owns (e.g. counts spanning the audit log) live in `analytics/queries/`. |
| D2 | **Live compute + short cache** | Dashboards compute on request; responses carry `X-Cache-Age` and a `lastUpdated` timestamp; a 5-min cache is a documented seam (EC-CACHE-01). **OD-1.** |
| D3 | **AuditLog hash chain** (F-239) | Each row stores `prev_hash` (last row in the tenant's chain) and `row_hash = sha256(canonical(fields) + prev_hash)`. Append-only via the queries layer (no update/delete helper). An on-demand `verify_chain(tenant)` walks it (EC-PRIV-06). **OD-3.** |
| D4 | **Snapshot-at-request** (F-064/EC-RPT-03) | An export captures its rows at request time into the `ReportExport.snapshot`/file; later mutations don't change a generated report. |
| D5 | **Export execution** | Small reports (≤ a row threshold) computed **synchronously**, returned inline + recorded as a `ReportExport`. Large ones create a `ReportExport(status=queued)` and return a job id (Celery seam, F-063). Storage key stubbed (S3 presign later, F-236). **OD-2.** |
| D6 | **RBAC scoping** | Role dashboards are strictly caller-scoped: faculty/student/parent see only their own; admin → their branch; super_admin → all branches in tenant (F-021/F-025). Audit read = admin/super_admin; SupportModeLog = platform_owner. |
| D7 | **Audit emit points** | `record_audit()` is wired into the **high-value** sensitive mutations already built — `result.publish`, `payroll.run`/`lock`, `refund.create`, retroactive attendance edit, rollover execute/undo, employee deactivate, tenant/seat actions — plus a documented list for the rest. **OD-4.** |

---

## 3. Models (`apps/analytics/models/`)

All extend `core.BaseModel` except where immutability needs raw fields.

### 3.1 `logs.py`
- **`AuditLog`** (F-239, append-only) — `tenant`, `actor_user` (null=system), `action`,
  `entity_type`, `entity_id`, `diff` JSONB, `ip_address`, `user_agent`, `correlation_id`,
  `prev_hash`, `row_hash`. Index `(tenant, created_at)`, `(tenant, action)`. **No update/delete
  query helpers** (immutability enforced in the queries layer; DB trigger is an Ops seam).
- **`SupportModeLog`** (F-240) — `platform_owner`, `tenant`, `started_at`, `ended_at`,
  `reason`, `ticket_ref`, `read_only`, `actions` JSONB.

### 3.2 `data_ops.py`
- **`ReportExport`** (F-062/063/064/236) — `tenant`, `branch` (null), `report_type`,
  `params` JSONB, `status` (`queued|running|ready|failed|timed_out`), `row_count`,
  `snapshot` JSONB (small) / `file_key` (large, stubbed), `requested_by`, `expires_at`,
  `error`. Index `(tenant, status, created_at)`.
- (DSAR `DataExport`/`DataDeletion` deferred — see §1 out-of-scope.)

---

## 4. The surfaces (the heart)

### 4a. Dashboards — `interactors/dashboard.py`
Pure composition. e.g. `admin_dashboard(branch)` →
`{ presentToday, feeCollectedToday, classesRunning, alerts: { lowAttendance[], pendingFees[],
upcomingExams[] } }`, each field from the owning module's query
(`attendance.report.shortage_report`, fees collection metrics, exam slots).
`faculty_dashboard(user)`, `student_dashboard(user)`, `parent_dashboard(user, child)` —
caller-scoped (D6). `super_admin_dashboard(tenant)` loops branches and rolls up
students/faculty/fees/attendance % + branch-comparison rows (F-021/F-022) and
consolidated-defaulter / exam-comparison (F-038/F-039).

### 4b. Audit — `interactors/audit.py` + `queries/audit.py`
`record_audit(*, tenant, actor, action, entity_type, entity_id, diff, request=None)`:
inside the caller's transaction, fetch the tenant's last `row_hash` (locked), compute the new
`row_hash`, insert. `list_audit(tenant, filters, cursor)` (F-299 cursor). `verify_chain(tenant)`
recomputes hashes to detect tampering (EC-PRIV-06).

### 4c. Reports/exports — `interactors/report.py`
`generate_report(*, tenant, branch, report_type, params, requester)`: resolve rows via the
owning module's query **at request time** (D4); if `row_count` ≤ threshold → compute inline,
store `snapshot`, status `ready`; else create `queued` job (Celery seam). NAAC export
(F-237) collects fields, returns `{ data, missingFields[] }`, never blocks on gaps.

---

## 5. Endpoint surface (`/api/v1/analytics/`)

**Dashboards** `GET dashboard/admin/` · `GET dashboard/faculty/` · `GET dashboard/student/` ·
`GET dashboard/parent/?childId=` · `GET dashboard/collection/` (F-138) ·
`GET dashboard/super-admin/` (F-021/022/025/038/039)
**Audit** `GET audit/` (admin/super_admin, filtered + cursor) · `GET audit/verify/` (integrity) ·
`GET support-mode/` (platform_owner)
**Reports** `POST reports/` (request a module report/export) · `GET reports/{id}/` (status +
inline data or signed-key) · `GET reports/naac/` (F-048/237)

---

## 6. Edge cases — the spec (where each is enforced)

| Code | Rule | Enforced in |
|------|------|-------------|
| **F-064 / EC-RPT-03** | Live data changes during export → report reflects request-time snapshot | `generate_report` captures rows once (D4) |
| **EC-RPT-01 / F-063** | 10,000-row export → background job + link, not inline | `generate_report` threshold → `queued` job |
| **EC-CEL-02** | Export > 30 min → `timed_out`; partial cleanup; admin notified | `ReportExport.status=timed_out` (sweeper seam) |
| **EC-CEL-09** | Stale export heartbeat > 5 min → orphan-swept `timed_out` | status + heartbeat seam |
| **EC-CACHE-01** | Dashboard aggregate stale ≤ 5 min → 200 + `X-Cache-Age`; `lastUpdated` shown | dashboard response headers (D2) |
| **F-239 / EC-PRIV-06** | Audit row tampered → chain break detected | `verify_chain` recompute (D3) |
| **F-239** | No UPDATE/DELETE on audit rows | queries layer exposes insert/read only |
| **F-237** | NAAC export with missing fields → list gaps, still export | NAAC report `missingFields[]` |
| **F-021 / F-025 / F-038 / F-039** | Super-admin sees only own-tenant branches, aggregated + drill-down | super_admin dashboard scoping (D6) |
| **F-051 / F-181 / F-196 / F-211** | Each role dashboard scoped to caller | per-role interactor + permission |
| **EC-RBAC-05 (reuse)** | Faculty/student/parent can't read another's dashboard data | caller-scoped resolution |

---

## 7. Architecture (non-negotiable)

Thin views → interactors → queries; **`.objects`/`.save()` only in `queries/`**. Analytics
**composes other modules through their query/interactor layers** — a stray cross-app
`.objects` is the failure mode to guard. Verify:
`grep -rn "\.objects\.\|\.save(" apps/analytics/{views,interactors}` → empty, and
`grep -rn "fees\.\|attendance\.\|examinations\.\|admissions\.\|hr\." apps/analytics/interactors | grep "\.objects"` → empty.

---

## 8. File-by-file build plan

```
enums.py                 ReportStatus, AuditAction (or free-form), SupportMode
models/logs.py           AuditLog, SupportModeLog
models/data_ops.py       ReportExport
queries/audit.py         insert (hash-chain), list (cursor), last_hash (locked), verify
queries/report.py        ReportExport CRUD; analytics-owned aggregate reads
interactors/dashboard.py admin/faculty/student/parent/collection/super-admin composition
interactors/audit.py     record_audit, verify_chain
interactors/report.py    generate_report (snapshot, threshold), naac_export
serializers/ views/ urls dashboards, audit, reports
admin.py                 register (read-only for AuditLog)
tests/                   one test per F/EC (below)
```
Then `makemigrations analytics`, `migrate`, `check`, `makemigrations --check`.

---

## 9. Testing plan

`env`: tenant + 2 branches + admin + super_admin + a faculty/student/parent + seeded
attendance/fees/exam/enrollment data (reuse factories from prior stages). Tests:
- **Dashboards:** admin snapshot returns present/fee/alerts; super-admin rolls up both branches;
  each role dashboard is caller-scoped (cross-role read denied).
- **Audit:** `record_audit` chains `prev_hash`→`row_hash`; `verify_chain` passes; a manual row
  mutation makes `verify_chain` fail (EC-PRIV-06); no update/delete helper exists.
- **Reports:** small report → inline snapshot, status `ready`; large (mock high count) →
  `queued` job id (EC-RPT-01); snapshot doesn't change after a later data mutation (F-064);
  NAAC export lists `missingFields` and still returns data (F-237).
- **Cache header:** dashboard response carries `X-Cache-Age` / `lastUpdated` (EC-CACHE-01).
- Full suite stays green (currently **230**) + **zero** ORM-outside-queries.

Command unchanged:
```
export PATH="$HOME/.local/bin:$PATH" && unset USE_POSTGRES DATABASE_URL && \
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest -p no:cacheprovider -q
```

---

## 10. Build order (sub-stages) & effort

| Sub-stage | Content | Effort |
|-----------|---------|--------|
| 9.0 | Enums + models + migration | S |
| 9.1 | Audit: hash-chain insert + list + verify (F-239, EC-PRIV-06) | M |
| 9.2 | Wire `record_audit` into high-value mutations (D7) | M |
| 9.3 | Role dashboards: admin/faculty/student/parent/collection (F-051/053/138/181/196/211) | **L** |
| 9.4 | Super-admin cross-branch consolidation + comparison + defaulter + exam (F-021/022/025/038/039) | M |
| 9.5 | Reports + snapshot exports + threshold/job seam (F-062/063/064/236, EC-RPT-01/03) | M |
| 9.6 | NAAC export with gaps (F-048/237) | S |
| 9.7 | SupportModeLog (F-240) | S |
| 9.8 | Tests (all F/EC) + full-suite green + queries scan | M |

9.3 (role dashboards) is the most work — composing five modules per role with correct scoping.

---

## 11. Decisions (resolved — confirmed by the product owner)

- **OD-1 — dashboard compute: LIVE ON REQUEST.** Compute fresh per call; responses carry
  `X-Cache-Age` + `lastUpdated`; a 5-min cache stays a documented seam (EC-CACHE-01).
- **OD-2 — export execution: FULL CELERY + S3 NOW.** Real Celery task pipeline and an S3
  storage layer for report exports. Small reports may still resolve inline, but the export
  job, status lifecycle, signed-download URL, and cleanup are built for real. **Build note:**
  tests run with `CELERY_TASK_ALWAYS_EAGER=True` (tasks execute synchronously in-process) and
  a **`SandboxS3` adapter** (records the upload, returns a deterministic stub signed URL) —
  so the full pipeline is exercised end-to-end with **no live broker/AWS**; production swaps
  the broker (Redis) and `LiveS3` via settings, exactly like `payments.get_gateway()`. This
  adds: a Celery app config + broker settings, `analytics/tasks.py` export tasks, and
  `integrations/adapters/s3.py` (sandbox + live + factory). Covers EC-RPT-01/CEL-02/CEL-09
  (timeout → `timed_out`, partial-file cleanup, orphan sweep) for real.
- **OD-3 — audit hash chain: IMPLEMENT NOW.** `prev_hash`/`row_hash` chain + on-demand
  `verify_chain(tenant)`; tamper detection is testable (EC-PRIV-06). Nightly verifier daemon
  stays an Ops seam.
- **OD-4 — audit coverage: HIGH-VALUE ACTIONS NOW.** Wire `record_audit` into result.publish,
  payroll run/lock, refund.create, retroactive attendance edit, rollover execute/undo,
  employee deactivate, tenant/seat actions; a documented list covers the rest incrementally.

---

## 12. Risks

- **Cross-app boundary** is the dominant risk: analytics must aggregate via other modules'
  query/interactor layers, never their models — a single `fees.models...objects` call breaks
  the architecture and the scan.
- **Audit chain correctness** — `record_audit` must read the tenant's last hash under a lock
  and write atomically inside the caller's transaction, or concurrent writers fork the chain;
  `verify_chain` is the guard and must catch both tampering and forks.
- **Snapshot semantics (F-064)** — a report must freeze its rows at request time; the test
  mutates data after generation and asserts the report is unchanged.
- **Dashboard scoping (D6)** — a faculty/student/parent must never see another person's or
  branch's aggregates; each role path needs an explicit scoping test, not just happy-path.
- **Double JobRun** — `ReportExport` is analytics' own job record; if/when the integrations
  `JobRun` (Stage 8) lands, reconcile so exports don't track state in two places.
```
