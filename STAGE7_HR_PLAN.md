# Stage 7 — HR & Payroll: Detailed Implementation Plan

> Same discipline as Stages 1–6: per-entity models, **all ORM in `queries/`**, thin views →
> interactors (`@transaction.atomic`) → queries, camelCase serializers, optimistic `version`,
> **money as integer paise** (reuse `fees/helpers/paise.py`), banker's rounding for display.
> This is the most sensitive module after Fees — it moves money and has hard immutability,
> RBAC, and conflict-of-interest rules. Plan carefully; the edge-case table (§6) is the spec.

---

## 0. Current state of the app

`apps/hr/` is a **registered but empty skeleton** — in `INSTALLED_APPS` (`base.py:69`) and
`config/urls.py` (`api/v1/hr/`). The tree exists (models `employee`/`leave`/`payroll`;
queries/interactors/serializers/views split the same way; `enums.py`, `tasks.py`, tests),
but **every file is a TODO stub** (0 models, 0 logic, 0 tests). Greenfield.

Two existing structures it must reconcile with (see §2):
- **`accounts.FacultyProfile`** already holds `designation`, `employment_type`,
  `date_of_joining`, `date_of_leaving`, qualifications — teaching/HR overlap.
- **`attendance.LeaveRequest`** already models leave with an `applicant_role` (student **or**
  employee) and an `employee` FK + approve/reject workflow — but **no balances**.

---

## 1. Goal & scope

Deliver the branch-admin HR suite (F-156 – F-170) plus the faculty self-service slices
(F-162/F-165/F-190/F-194):

1. **Employee master** (F-156/F-169) — HR records for all staff types, deactivation that
   excludes from future payroll.
2. **Multi-branch faculty** (F-161/EC-DATA-05/EC-RBAC-08) — `BranchFaculty` join with exactly
   one **salary branch** per faculty (partial-unique), used by payroll.
3. **Leave with balances** (F-157/F-162/F-163) — apply / approve / reject + per-type balance
   accrual and decrement; conflict-of-interest routing.
4. **Salary component templates** (F-166) — reusable earnings/deductions.
5. **Payroll run** (F-158/F-164/F-167) — compute payslips for active employees with pro-rata
   for mid-month join/exit; **immutable once locked**; corrections via `PayrollAdjustment`.
6. **Payslips** (F-159/F-165/F-194) — per-employee computed slip + PDF; faculty sees only
   their own (F-165/EC-RBAC-05).
7. **HR reports** (F-168) — headcount + leave-summary aggregates.
8. **Compliance exports** (F-160) — **basic** Form-16 / PF summary exports (per-employee
   annual earnings + PF/tax totals as CSV/PDF); admin for all, faculty for their own.
9. **HR documents** (F-170) — contract/document storage (S3 key stubbed now).

**Out of scope (later):** real S3/CloudFront presign for payslip/Form-16 PDFs (F-301 — we
generate bytes + stub key), real Celery + crash-recovery for payroll (F-267/EC-CEL-01 — we
run synchronously inside one `@transaction.atomic` so partial payslips roll back, leaving the
async seam), step-up auth on `payroll.run` (F-262 — Auth-stage seam, enforced as a documented
hook), column-level PII encryption of `bank_account` (F-281 — store plaintext-capable field
now behind a single accessor, swap to pgcrypto later). Note: F-160 Form-16/PF is in scope but
only as a **basic** earnings/PF/tax **summary export** (not statutory-grade tax filing).

---

## 2. Critical dependencies & decisions

| # | Decision | Resolution |
|---|----------|-----------|
| D1 | **Employee vs FacultyProfile** | `Employee` is the **HR master** keyed 1:1 to `accounts.User` (any staff role: faculty/admin/support), holding `employee_code` (UNIQUE per tenant), `employment_type`, `joined_at`, `exited_at`, base-salary components, bank details, document keys. `FacultyProfile` keeps **teaching** attributes only. For a faculty, `Employee.employee_code` equals their `User.custom_login_id` (the Employee ID they log in with) — documented, not duplicated logic. **OD-1.** |
| D2 | **Leave domain seam** | HR owns **staff leave with balances**: new `LeaveType`, `LeaveBalance`, and `hr.LeaveApplication`. The existing `attendance.LeaveRequest` **student** path is untouched; its *employee* path is superseded by HR (new staff leave goes through HR). HR leave approval does **not** drive attendance status (staff aren't in the % engine). **OD-2.** |
| D3 | **Money** | Integer paise everywhere (`BigIntegerField`), reuse `fees.helpers.paise` (`rupees_to_paise`, `paise_to_rupees_str`, banker's rounding). No floats. |
| D4 | **Payroll immutability** (F-164) | `PayrollRun.locked_at`. Once set, **no** payslip in the run may be updated/deleted; the queries layer refuses writes to a locked run; corrections create a `PayrollAdjustment` row in a *new* run. |
| D5 | **Salary branch** (F-161/EC-DATA-05) | `BranchFaculty(faculty, branch, is_salary_branch, role_at_branch JSONB)` with a **partial UNIQUE** on `(faculty, is_salary_branch=True)`. Payroll for a branch includes a multi-branch faculty **only** at their salary branch. |
| D6 | **Pro-rata** (F-167) | Mid-month join/exit → `net = full × worked_days / payable_days`, computed with `Decimal` + banker's rounding, on integer paise. Working/payable days respect the branch working-day calendar + holidays (F-309). |
| D7 | **Atomicity** (EC-CEL-01) | The whole run is one `@transaction.atomic`; any failure rolls back **all** payslips (no partial run). Run status: `pending → running → succeeded / failed`. Sync now; Celery seam documented. |
| D8 | **PDF** | Generate payslip bytes via an `hr/services/pdf.py` (reuse the examinations pattern); persist a `pdf_key` + size. Real presign deferred (F-301). |
| D9 | **PII** (F-281) | `Employee.bank_account` stored via a single field + accessor seam so encryption (pgcrypto/KMS) can be swapped in without touching call sites; plaintext acceptable in Phase 1 dev. |
| D10 | **Step-up auth** (F-262) | `payroll.run`, `payroll.lock`, and `employee.deactivate` are flagged as step-up-required; Phase 1 enforces a `requires_step_up=True` marker the view checks against a (stubbed) verified-step-up header, real TOTP in the Auth stage. |

---

## 3. Models (`apps/hr/models/`)

All extend `core.BaseModel` (UUID, timestamps, soft-delete, audit, `version`). Tenant/branch
scoped.

### 3.1 Enums (`enums.py`)
`EmploymentType` (full_time / part_time / contract / visiting) · `LeaveType`
(casual / sick / earned / unpaid) · `LeaveStatus` (pending / approved / rejected / cancelled) ·
`PayrollRunStatus` (pending / running / succeeded / failed / locked) · `ComponentKind`
(earning / deduction) · `ComponentCalc` (fixed / percent_of_basic).

### 3.2 `employee.py`
- **`Employee`** (F-156) — `user` (O2O accounts.User), `branch` (home branch),
  `employee_code` (UNIQUE per tenant), `employment_type`, `joined_at`, `exited_at` (null),
  `base_components` JSONB (snapshot of salary structure), `bank_account` (D9), `ifsc`,
  `pan`, `document_keys` JSONB, `is_active` (deactivation, F-169).
- **`BranchFaculty`** (F-161/D5) — `faculty` (FK User), `branch`, `is_salary_branch`,
  `role_at_branch` JSONB. **Partial UNIQUE** `(faculty)` where `is_salary_branch=True`.

### 3.3 `leave.py`
- **`LeaveBalance`** (F-157) — `employee`, `leave_type`, `balance_days` (Decimal),
  `accrual_rate` (Decimal/month), `year`. UNIQUE `(employee, leave_type, year)`.
- **`LeaveApplication`** (F-157/F-162/F-163) — `employee`, `leave_type`, `from_date`,
  `to_date`, `days` (computed, excludes holidays/weekends), `reason`, `status`,
  `approver` (FK User), `approved_at`, `decision_note`, `auto_routed_coi` (bool),
  `version`.

### 3.4 `payroll.py`
- **`SalaryComponent`** (F-166) — `branch`, `name`, `kind` (earning/deduction),
  `calc` (fixed/percent_of_basic), `amount_paise` / `percent`, `is_active`. Reusable template.
- **`PayrollRun`** (F-158/F-164) — `branch`, `period_month` (date, 1st of month),
  `status`, `locked_at` (null until locked), `executed_by`, `executed_at`,
  `totals` JSONB (gross/net/headcount), `error_message`. UNIQUE `(branch, period_month)`.
- **`Payslip`** (F-159) — `payroll_run`, `employee`, `components` JSONB (resolved lines),
  `gross_paise`, `deductions_paise`, `net_paise`, `worked_days`, `payable_days`,
  `pro_rated` (bool), `pdf_key`. **UNIQUE `(payroll_run, employee)`**.
- **`PayrollAdjustment`** (F-164) — `branch`, `employee`, `original_run` (FK),
  `amount_paise`, `reason`, `applied_in_run` (FK, null). Immutable corrections path.

---

## 4. Payroll run (the heart) — Flow / F-158/F-164/F-167

`RunPayrollInteractor.execute()` — one `@transaction.atomic` (EC-CEL-01 → all-or-nothing):

1. **Guards:** branch has no existing **locked** run for `period_month` (else 409); step-up
   verified (D10).
2. Create `PayrollRun(status=running)`.
3. `employees = hr.queries.list_payable_employees(branch, period_month)` — active, not
   exited before the month, and (for multi-branch faculty) **only at their salary branch**
   (D5/EC-DATA-05).
4. For each employee, inside the same transaction:
   - resolve `base_components` + branch `SalaryComponent` templates → earning/deduction lines;
   - compute `worked_days / payable_days` from join/exit + branch calendar (D6/F-309);
   - `gross`, `deductions`, `net` in paise with banker's rounding; pro-rate if partial month;
   - `create_payslip(...)` (UNIQUE `(run, employee)`); generate PDF bytes + `pdf_key` (D8).
5. Set run `succeeded`, write `totals`. Any exception → transaction rollback → **no partial
   payslips** (EC-CEL-01); run marked `failed` in a separate short transaction with the error.
6. **Locking** is a separate explicit action (`POST runs/{id}/lock/`): sets `locked_at`;
   thereafter the queries layer rejects any payslip write in that run (D4/F-164).

> Self-approval guard (EC-GUARD-15): if the executing admin shares a `linked_user_group_id`
> with any employee in the run, that employee's payslip line is **hard-blocked** from being
> finalized by them → routed to `super_admin`; audit `self_approve_blocked`.

---

## 5. Endpoint surface (`/api/v1/hr/`)

**Employees** `POST/GET/PATCH employees/` · `POST employees/{id}/deactivate/` (F-169, step-up) ·
`POST employees/{id}/branches/` (BranchFaculty; salary-branch toggle, F-161)
**Leave** `GET employees/{id}/leave-balances/` · `POST leave/` (apply, F-162) ·
`PATCH leave/{id}/decide/` (approve/reject, F-163; COI routing) · `GET leave/` (admin queue)
**Payroll** `POST/GET salary-components/` (F-166) · `POST payroll/runs/` (run, F-158, step-up) ·
`GET payroll/runs/{id}/` · `POST payroll/runs/{id}/lock/` (F-164, step-up) ·
`POST payroll/adjustments/` (F-164) · `GET payslips/` (admin) · `GET me/payslips/` (faculty,
F-165/F-194 — own only) · `GET payslips/{id}/pdf/` (RBAC-checked)
**Reports / compliance** `GET reports/headcount/` · `GET reports/leave-summary/` (F-168) ·
`GET reports/compliance/form16/` (F-160 — admin all / faculty own, basic PF+tax summary export)

---

## 6. Edge cases — the spec (where each is enforced)

| Code | Rule | Enforced in |
|------|------|-------------|
| **EC-CEL-01** | Worker crashes mid payroll → no partial payslips; run=failed; retryable | run interactor single `@transaction.atomic` (all-or-nothing) |
| **EC-DATA-05** | Multi-branch faculty salary uses the salary branch | `list_payable_employees` filters `BranchFaculty.is_salary_branch` |
| **EC-RBAC-05** | Faculty views colleague's payslip → 403 | payslip-PDF view RBAC (own `Employee` only) |
| **EC-RBAC-07** | Deactivate faculty who is also a linked parent → only that user_id off; parent unaffected | `deactivate_employee` toggles the single `user_id`; never touches linked rows |
| **EC-RBAC-08** | Multi-branch faculty → branch selector; JWT branch_id authoritative for writes | `BranchFaculty` list drives selector; writes use request branch (existing `resolve_branch`) |
| **EC-GUARD-15** | Payroll approver == employee (same `linked_user_group_id`) → hard block self-approve; route to super_admin | run/lock interactor self-approval guard + audit |
| **EC-GUARD-03** (staff analog) | Approver and applicant are the same person → cannot self-approve leave; auto-route | `decide_leave` COI check (`auto_routed_coi=True`) |
| **F-164 / EC-FORM-03** | Edit a locked run → 403; concurrent payslip edit → 409 version | locked-run write guard (queries) + optimistic `version` |
| **EC-API-05** | Stale `version` on PATCH → 409 with `currentVersion`; no partial write | version-checked update query |
| **F-167** | Mid-month join/exit → pro-rata net | run interactor pro-rata branch (D6) |
| **F-169** | Deactivated employee excluded from future payroll | `list_payable_employees` excludes `is_active=False` / `exited_at < month` |
| **F-165 / F-194** | Faculty sees only own payslips & Form-16 | `me/payslips` scoped to caller's `Employee` |
| **EC-NOT-01** | Payslip/notification to deactivated user skipped + logged | notification dispatch (Communications stage) reads `is_active`; HR marks intent |
| **F-309** | Leave/attendance respect working-day calendar + holidays; off-hour mutation audited | leave `days` calc + run `payable_days` use branch calendar; audit on off-hour writes |
| **F-262 (seam)** | Step-up before `payroll.run` / `lock` / `deactivate` | view-level `requires_step_up` marker (stub → real TOTP later) |
| **F-281 (seam)** | `bank_account` encrypted at rest | single accessor field (D9); pgcrypto swap later |
| Leave balance | Apply for more than balance (non-unpaid) → 400 insufficient balance | `apply_leave` balance check; decrement on approve, restore on reject/cancel |
| Overlap | Overlapping pending/approved leave for same employee → 400 | `apply_leave` overlap query |
| Duplicate run | Second `payroll.run` for same `(branch, month)` → 409 (idempotent) | UNIQUE `(branch, period_month)` + pre-check |

---

## 7. Architecture (non-negotiable)

Thin views → interactors (`@transaction.atomic`) → queries. **`.objects` / `.save()` /
`select_for_update` only in `queries/`.** Cross-app reads (accounts for the `User` /
`linked_user_group_id`, academics for the working-day calendar/holidays, organizations for
branch/tenant) go through **their query layers**. Verify after every change:
`grep -rn "\.objects\.\|\.save(\|select_for_update" apps/hr/{views,interactors,serializers}` → empty.

---

## 8. File-by-file build plan

```
enums.py                 all TextChoices
models/employee.py       Employee, BranchFaculty
models/leave.py          LeaveType(enum), LeaveBalance, LeaveApplication
models/payroll.py        SalaryComponent, PayrollRun, Payslip, PayrollAdjustment
queries/employee.py      employee + branch-faculty CRUD, list_payable_employees, deactivate
queries/leave.py         balance CRUD/decrement, application CRUD, overlap, COI lookup
queries/payroll.py       component/run/payslip/adjustment CRUD, locked-run write guard,
                         version-checked updates
services/pdf.py          payslip PDF bytes + key
services/payroll_calc.py pro-rata + component resolution (Decimal/paise, banker's rounding)
interactors/employee.py  create/update/deactivate (RBAC-07, step-up)
interactors/leave.py     apply (balance+overlap), decide (COI routing, balance move)
interactors/payroll.py   RunPayrollInteractor, lock_run, create_adjustment (immutability)
serializers/*.py         camelCase in/out (paise → rupee strings on display)
views/*.py + urls.py     endpoint surface (RBAC: faculty own-only)
admin.py                 register models
tests/                   one test per F / EC (below)
```

Then `makemigrations hr` (answer any non-null prompts as in prior stages), `migrate`,
`check`, `makemigrations --check`.

---

## 9. Testing plan (every F / EC gets a test)

`env` fixture: tenant + branch + working-day calendar/holidays + admin + 2 faculty
(`Employee` + `BranchFaculty`, one multi-branch with salary branch) + a support employee +
salary-component templates. Then:
- **Happy path:** run payroll → one `Payslip` per payable employee; gross/net in paise correct;
  lock → succeeds.
- One test per §6 row: **EC-CEL-01** (force an error mid-run → assert **zero** payslips
  persisted, run=failed), EC-DATA-05 (multi-branch faculty paid only at salary branch),
  EC-RBAC-05 (faculty GET other's payslip → 403), EC-RBAC-07 (deactivate faculty; linked
  parent still 200), EC-GUARD-15 (admin who is also a payable faculty → self-approve blocked),
  F-164 (edit locked run → 403), EC-API-05 (stale version → 409), F-167 (mid-month join →
  pro-rata net), F-169 (deactivated excluded next run), leave balance insufficient → 400,
  leave overlap → 400, duplicate run → 409.
- Money: assert paise integers and banker's-rounded rupee display strings.
- Full suite must stay green (currently **216**) + **zero** ORM-outside-queries.

Command (unchanged):
```
export PATH="$HOME/.local/bin:$PATH" && unset USE_POSTGRES DATABASE_URL && \
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest -p no:cacheprovider -q
```

---

## 10. Build order (sub-stages) & effort

| Sub-stage | Content | Effort |
|-----------|---------|--------|
| 7.0 | Enums + all models + migration + admin | M |
| 7.1 | Employee + BranchFaculty CRUD + deactivation (F-156/161/169, EC-RBAC-07/08) | M |
| 7.2 | Salary components + leave balances/applications + COI routing (F-157/162/163/166, EC-GUARD-03) | M |
| 7.3 | **Payroll run**: component resolution, pro-rata, atomic all-or-nothing (F-158/167, EC-CEL-01/DATA-05) | **L** |
| 7.4 | Immutability + adjustments + lock (F-164, EC-FORM-03/API-05) | M |
| 7.5 | Payslips + PDF + faculty own-only RBAC (F-159/165/194, EC-RBAC-05) | M |
| 7.6 | Self-approval guard + step-up markers (EC-GUARD-15, F-262 seam) | S |
| 7.7 | HR reports (F-168) | S |
| 7.8 | Tests (all F/EC) + full-suite green + queries scan | M |

Payroll run (7.3) carries the real complexity — money math, pro-rata, multi-branch salary,
and the all-or-nothing transaction.

---

## 11. Decisions (resolved — all confirmed by the product owner)

- **OD-1 — Employee vs FacultyProfile: SEPARATE `Employee` MASTER.** A standalone `Employee`
  linked 1:1 to `User` (covers faculty, admin, support); `FacultyProfile` keeps only teaching
  attributes. Faculty `employee_code` mirrors `User.custom_login_id`.
- **OD-2 — staff leave: NEW HR LEAVE SYSTEM.** `hr.LeaveApplication` + `LeaveBalance` own
  staff leave with balance accrual/decrement; the `attendance.LeaveRequest` employee path is
  superseded; student leave in attendance is untouched.
- **OD-3 — payroll execution: SYNCHRONOUS, ALL-OR-NOTHING.** One `@transaction.atomic`; any
  failure rolls back every payslip (EC-CEL-01). Celery/background processing is a documented
  later seam.
- **OD-4 — storage/PII: SIMPLE NOW, HARDEN LATER.** `bank_account` in a plain field behind a
  single accessor; payslip PDF bytes generated with a stubbed storage key. pgcrypto encryption
  + S3/CloudFront presign land in the security/Operations stage.

---

## 12. Risks

- **Money correctness** is paramount: every component, gross, deduction, net, and pro-rata is
  integer paise with banker's rounding — a float anywhere is a defect. Tests assert exact
  paise.
- **Immutability (F-164)** must be enforced in the **queries layer**, not just the view, so no
  code path can mutate a locked run; the test edits a locked run and expects 403.
- **All-or-nothing run (EC-CEL-01)** depends on a single transaction wrapping the whole loop —
  PDF generation and every payslip insert must be inside it so a late failure leaves zero rows.
- **Conflict-of-interest (EC-GUARD-15)** and **RBAC own-only (EC-RBAC-05)** are the security
  surface — a faculty must never read another's salary, and an admin who also draws salary must
  never self-approve; both need explicit tests, not just happy-path coverage.
- **Multi-branch salary (EC-DATA-05)** is the subtle correctness trap: a faculty teaching at
  two branches must appear in exactly one branch's payroll (the salary branch) — the partial
  unique + the payable-list filter are the guard.
- **Leave-balance integrity:** approve decrements, reject/cancel restores; concurrent decisions
  must not double-spend a balance — use `select_for_update` on the balance row in the queries
  layer.
