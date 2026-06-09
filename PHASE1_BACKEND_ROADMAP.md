# EduOS Backend — Phase 1 Completion Roadmap

> **Scope of this document:** A code-level audit of the Django 5 + DRF backend (`eduOS-backend/`) and an ordered, feature-by-feature plan to complete the **Phase 1 — Admin Portal (Branch Admin)** backend, i.e. the API surface required to serve the nine admin modules defined in `ERP-PRD/PRD/implementation_plan.md`.
>
> **Audit date:** based on the current state of the repo (3 apps migrated, 45 DB tables).

---

## 1. Executive Summary

The backend has a **strong foundation and a complete authentication layer**, but the **business domains are almost entirely unbuilt**. The project is best described as *"reference implementation + scaffolding."*

| Layer | State | Notes |
|---|---|---|
| Project infra (Django, DRF, Celery, settings, Docker, CI tooling) | ✅ Complete | Solid, production-shaped |
| `core` (BaseModel, tenant/branch scoping) | ✅ Complete | All domain models inherit this |
| `accounts` (auth, users, profiles) | ✅ Complete | Full layered build + ~880 lines of tests — **this is the reference pattern** |
| `organizations` (tenant/branch) | 🟡 Models done, API ~10% | Only `tenant-config` endpoint exists |
| `academics` | 🟡 Models done, API 0% | 13 models migrated; no views/serializers/urls |
| `admissions`, `attendance`, `examinations`, `fees`, `hr`, `communications` | 🔴 Scaffold only | Empty model/view files with TODO docstrings; no migrations |
| `analytics`, `integrations` | 🔴 Scaffold only | Needed for Dashboard + Reports + Razorpay/SMS |

**Rough Phase 1 backend completion: ~25%.** Auth and the data foundation are done; 6 of the 9 admin modules have zero backend, and 2 more (academics, organizations) have models but no API.

---

## 2. What Is Complete

### 2.1 Foundation & Infrastructure ✅
- Django 5.1 + DRF project with split settings (`config/settings/` dev/prod), `config/urls.py` routing all 11 API namespaces under `/api/v1/`.
- **Celery + Redis** wired (`django-celery-beat`, `django-celery-results` tables present) — async task infra ready, but **no tasks written yet** (every `tasks.py` is empty).
- **`core` app** provides the shared base every model uses:
  - `BaseModel` — UUID PK, `created_at`/`updated_at`, soft-delete (`is_active`), audit (`created_by`/`updated_by`), and an optimistic-concurrency `version` field.
  - `TenantScopedMixin` / `BranchScopedMixin` — multi-tenant FK scoping.
- Tooling: Docker + docker-compose, Makefile, pytest (+pytest-django, factory-boy), ruff/black/isort/mypy, migration linter.
- DB migrated and seedable (`seed_db.py`, 45 tables live).

### 2.2 `accounts` — Authentication ✅ (Reference Implementation)
This is the **only fully-built app** and establishes the architecture every other feature must follow.

- **Models:** `Role`, `User` (custom, multi-identifier login), `RefreshToken`, `OTPRecord`, `InviteToken`, `LoginAttempt`, `FacultyProfile`, `StudentProfile`, `GuardianProfile`, `StudentGuardianLink`.
- **Endpoints (live under `/api/v1/auth/`):** `login`, `refresh`, `logout`, `me`, `password/change`, `password/reset/request`, `password/reset/verify`, `invite/create`, `invite/accept`.
- **Layered architecture:** `views → interactors (business logic) → queries (reads) → serializers → dtos`, plus `backends.py`, `tokens.py`, `permissions.py`, `validators.py`, `admin.py`.
- **Tests:** ~880 lines across models, views, queries, serializers, interactors.
- **Gaps within accounts:** `views/mfa.py`, `views/session.py`, `views/user.py` are empty (MFA, session management, admin user-CRUD not yet built — MFA is Platform-Owner Phase 6, so not Phase 1 critical).

### 2.3 `organizations` — Tenant/Branch 🟡
- **Models done & migrated:** `Tenant`, `Branch`, `TenantSettings`, `PlanSubscription`.
- **Only one endpoint:** `GET /tenant-config/` (drives the frontend login page).
- **Empty stubs:** `branch`, `institution`, `plan`, `feature_flag` views — no branch CRUD, no settings API.

### 2.4 `academics` — Models 🟡
- **13 models done & migrated:** `Subject`, `BatchSubject`, `BatchFaculty`, `BatchFacultyRole`, `AcademicYear`, `AcademicPeriod`, `Holiday`, `Department`, `Course`, `Batch`, `PeriodSlot`, `Room`, `Timetable`, `TimetableEntry`.
- **API layer is 0%:** no views, serializers, urls, interactors, or queries. `urls.py` is `# TODO: Add academics endpoints`.

---

## 3. What Is NOT Complete

| App | Models | Migrations | Serializers | Views/API | URLs | Tests | Phase 1 module it powers |
|---|---|---|---|---|---|---|---|
| `academics` | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | Academics |
| `organizations` | ✅ | ✅ | ❌ | 🟡 1 ep | 🟡 | 🟡 | (cross-cutting: branch/settings) |
| `admissions` | ❌ TODO | ❌ | ❌ | ❌ | ❌ | ❌ (empty) | Admissions |
| `attendance` | ❌ TODO | ❌ | ❌ | ❌ | ❌ | ❌ (empty) | Attendance + Dashboard |
| `examinations` | ❌ TODO | ❌ | ❌ | ❌ | ❌ | ❌ (empty) | Examinations |
| `fees` | ❌ TODO | ❌ | ❌ | ❌ | ❌ | ❌ (empty) | Fees + Dashboard |
| `hr` | ❌ TODO | ❌ | ❌ | ❌ | ❌ | ❌ (empty) | HR |
| `communications` | ❌ TODO | ❌ | ❌ | ❌ | ❌ | ❌ (empty) | Communications |
| `analytics` | ❌ TODO | ❌ | ❌ | ❌ | ❌ | ❌ (empty) | Dashboard + Reports |
| `integrations` | ❌ TODO | ❌ | ❌ | ❌ | ❌ | ❌ (empty) | Razorpay (Fees), SMS (Comms) |

> All scaffold-only apps already contain helpful TODO docstrings naming the *suggested models* per file (e.g. `fees/models/structure.py` → `FeeStructure, Concession, StudentFeeAssignment`). Use these as the starting spec.

**Also missing globally:** per-app `permissions.py` (only `accounts` has one), any Celery `tasks.py` content (bulk import, large exports, SMS dispatch, payment reconciliation all need async tasks), and DRF-level RBAC enforcement on the new endpoints.

---

## 4. The Build Pattern (Follow `accounts` Every Time)

Before building any module, internalise the established layered flow. **Do not put business logic in views or serializers.** Each module is built in this dependency order:

```
1. models/         → domain tables (inherit BaseModel + Tenant/BranchScopedMixin)
2. makemigrations  → migrate
3. admin.py        → register for Django admin (fast manual QA)
4. factories.py    → factory-boy factories for tests + seeding
5. dtos.py         → typed response objects
6. serializers/    → input validation + output shaping ONLY
7. queries/        → THE DATA-ACCESS LAYER: ALL ORM calls live here —
                     reads (get/filter/count/aggregate) AND writes
                     (create/update/soft_delete). Tenant/branch-scoped.
8. interactors/    → business logic / orchestration / transactions (use cases).
                     Calls query functions; NEVER touches .objects directly.
9. views/          → thin: validate → call interactor (writes) or query (reads) → return DTO
10. permissions.py → role-based access (admin/faculty/etc.)
11. urls.py        → wire endpoints; confirm in config/urls.py
12. tests/         → models, queries, interactors, serializers, views
```

**Repository rule — all DB access goes through `queries/`.** No raw `.objects` / `.save()` / `.create()` calls anywhere outside the `queries/` layer. Views and interactors must call query functions. Note: the current `accounts` app does NOT fully follow this yet (its interactors call `InviteToken.objects.create()` / `user.save()` directly) — bring those into line when refactoring, and build all new modules to the rule from the start.

**Read path vs write path:**
- *Read endpoint:* `View → query (returns data) → DTO`. No interactor needed.
- *Write endpoint:* `View → interactor (rules + @transaction.atomic) → query (does the create/update) → DTO`. The transaction boundary stays in the interactor; the actual ORM mutation happens inside the query function it calls.

**Cross-cutting rules for every endpoint:**
- All querysets filtered by `tenant` (and `branch` where applicable) from the authenticated user — never trust a client-supplied tenant id.
- Mutations use `version` for optimistic concurrency (the PRD's `EC-CONCUR-*` cases).
- Soft-delete via `BaseModel.soft_delete`, never hard delete.
- Money as integer paise / `Decimal`, never float (Fees).
- Long-running work (bulk CSV, large exports, SMS blasts, reconciliation) → Celery task, return a job id the client polls.

---

## 5. Phase 1 Backend Roadmap (Ordered)

Sequenced by dependency. Each step assumes the full Section-4 pattern. Effort estimates are rough engineer-days for one developer.

### Stage 0 — Unblock the foundation (½–1 day) — ✅ DONE
Finish the cross-cutting pieces every later module leans on.
1. ✅ **`organizations` API:** branch CRUD, tenant settings read/update, plan info, subdomain check — plus the platform-owner tenant-management endpoints (list/create/detail/activate-deactivate with session-kill).
2. ✅ **Shared role permissions:** `accounts/permissions.py` (`IsSuperAdmin`, `IsAdmin`, `IsAdminOrSuperAdmin`, `IsPlatformOwner`, …) is imported and reused across apps. Object-scoped perms (`IsBranchAdmin`, `IsFacultyOfBatch`) are deferred to the modules that need them.
3. ✅ **Seed data:** `seed_db.py` provisions both reference institutions end-to-end — Greenfield Academy (school, starter) + Horizon Engineering College (college, growth), each with primary branch, `TenantSettings`, `PlanSubscription`, three `TenantQuota` counters, and super-admin/admin/faculty/student users, plus a tenant-less platform owner. Idempotent; verified by `apps/organizations/tests/test_seed.py`.

### Stage 1 — Academics API (2–3 days) — *unblocks everything*
Models already exist; only the API layer is missing. **Do this first** — admissions, attendance, exams, and fees all FK into `Batch`/`Subject`/`AcademicYear`.
- Serializers + queries + viewsets for: AcademicYear & AcademicPeriod, Department/Course/Batch hierarchy, Subject + BatchSubject, BatchFaculty (incl. class-teacher assignment, school-only), Room + PeriodSlot.
- **Timetable** endpoints with **clash detection** (faculty + room) — `EC-TT-01/02`. This is interactor logic, not a serializer.
- Holiday calendar CRUD — `EC-ATT-01`.
- Academic-year **rollover wizard** endpoint (preview + commit, transactional) — `Flow 7`, `EC-ROL-01–05`. Heaviest item; consider a Celery task for the commit.
- *Powers admin module: **Academics**.*

### Stage 2 — Attendance (2 days)
- Models: `AttendanceSession`, `AttendanceRecord`, `LeaveRequest` (+ enums) → migrate.
- Endpoints: real-time board across classes, shortage/detention reports (`F-105/115`), leave approval queue (`F-106`), retroactive correction with audit diff (`F-107`, `EC-ATT-04`), monthly/subject reports (`F-110`), late-marking audit log (`F-108`).
- Live counter: expose a polling endpoint (frontend mocks WebSocket via polling).
- *Powers admin module: **Attendance** + feeds **Dashboard**.*

### Stage 3 — Fees (3–4 days) — *highest complexity*
- Models: `FeeStructure`, `Concession`, `StudentFeeAssignment`, `FeeInvoice`, `Payment`, `Receipt`, `Refund` → migrate. **Use `Decimal`/integer paise.**
- Endpoints: fee structure per batch (`F-136`), concession/scholarship approval workflow (`F-137`), collection dashboard (`F-138`), defaulter list with escalation (`F-139`), installment plans + balance (`F-140`, `EC-FEE-05`), reconciliation (`F-143`), duplicate→refund (`F-144`, `EC-FEE-04`), **sequential receipts** (`F-145`, `EC-FEE-09` — needs a DB-level counter/lock), retroactive scholarship credit note (`F-151`), ₹0 fee handling.
- **Razorpay**: build against `integrations` (Stage 7) but stub the gateway first so the flow works without live keys (`Flow 5`).
- Celery: payment reconciliation + receipt generation tasks.
- *Powers admin module: **Fees** + feeds **Dashboard**.*

### Stage 4 — Examinations (3 days)
- Models: `Exam`, `ExamSchedule`, `HallTicket`, `Seating`, `MarksEntry`, `Result`, `Assignment` → migrate.
- Endpoints: exam schedule CRUD + hall clash detection (`F-116`, `EC-EXAM-06`), auto seating (`F-118`), invigilator assignment (`F-119`), marks-entry oversight + deadlines (`F-120`), **two-step result publish** (`F-122`, `Flow 6`), revision history (`F-123`), analytics (`F-124`), hall tickets gated on exam-fee paid (`F-117`, `EC-EXAM-01`).
- College-only: CGPA/SGPA, arrears, grace marks (`F-045–050`) — guard with institution type.
- *Powers admin module: **Examinations**.*

### Stage 5 — Admissions (2–3 days)
- Models: `Enquiry`, `Application`, `Enrollment`, `Waitlist` → migrate.
- Endpoints: enquiry capture (`F-071`), pipeline stage transitions (`F-072`), step-resume wizard state (`F-073`), eligibility screening (`F-074`), merit list (`F-075`), enrollment provisioning with **duplicate detection** (`F-080`, `EC-DATA-03`), parent invite reusing `accounts` invite flow (`F-081`), **bulk CSV upload** with failed-row report (`F-068` → Celery task), waitlist (`F-084`), transfer (`F-085`).
- *Powers admin module: **Admissions**.*

### Stage 6 — HR (2 days)
- Models: `Employee`, `LeaveRequest`/`LeaveBalance`, `PayrollRun`/`Payslip` → migrate.
- Endpoints: employee master (`F-156`), leave apply/approve (`F-157/163`), **payroll run with step-up auth** (`F-158`, `EC-GUARD-15`), salary slip PDF (`F-159` → Celery/PDF), Form-16/PF export stubs (`F-160`), multi-branch assignment (`F-161`), pro-rata (`F-167`), HR reports (`F-168`).
- *Powers admin module: **HR**.*

### Stage 7 — Communications + Integrations (2 days)
- `integrations` first: provider models + adapters for **MSG91 (SMS)**, **Razorpay**, **S3** with health checks (`F-015`); keep a mock/sandbox mode toggle.
- `communications`: announcements with role/batch targeting (`F-171`), SMS delivery status per recipient (`F-174` → async dispatch + webhook callback), bulk rate-limit indicator (`F-175`), notification preferences (`F-179`).
- *Powers admin module: **Communications**.*

### Stage 8 — Dashboard + Reports / Analytics (2 days) — *do last, it aggregates everything*
- `analytics`: aggregation queries for the admin dashboard — today's present %, fee collected today, classes running (`F-051`), alert feeds (`F-053`).
- Reports: module-wise downloadable exports (`F-062`), **large export job status** (`F-063`, `EC-RPT-01` → Celery + polling), NAAC/NIRF export college-only (`F-048/237`).
- *Powers admin modules: **Dashboard** + **Reports**.*

---

## 6. Suggested Order at a Glance

```
Stage 0  Foundation (orgs API, shared perms, seed)        ~1d
Stage 1  Academics API            ◀ unblocks all          ~2–3d
Stage 2  Attendance                                        ~2d
Stage 3  Fees              ◀ most complex                  ~3–4d
Stage 4  Examinations                                      ~3d
Stage 5  Admissions                                        ~2–3d
Stage 6  HR                                                ~2d
Stage 7  Communications + Integrations                     ~2d
Stage 8  Dashboard + Reports  ◀ aggregates, do last        ~2d
                                              ≈ 19–22 dev-days
```

## 7. Definition of Done (per module)
- [ ] Models inherit `BaseModel` + correct scoping mixin; migrations applied cleanly.
- [ ] All reads tenant/branch-scoped to the authenticated user.
- [ ] All DB access (reads + writes) goes through `queries/`; no `.objects`/`.save()`/`.create()` outside that layer.
- [ ] Business rules + transactions live in interactors; views are thin.
- [ ] RBAC enforced via `permissions.py`.
- [ ] Relevant `EC-*` edge cases from the PRD have explicit tests.
- [ ] Endpoints match the URL shapes the `apps/institution` frontend services expect.
- [ ] Registered in Django admin + factory-boy factory for seeding.
- [ ] Test coverage parity with `accounts` (models/queries/interactors/serializers/views).

## 8. First Concrete Step
Start with **Stage 1, Academics serializers** — the models are already migrated, so you get a working API the same day and immediately unblock attendance/fees/exams. Copy `apps/accounts/{serializers,queries,interactors,views,urls}.py` structure verbatim and adapt.

---

## Appendix A — Multi-Tenant Identity Model (Design Decision)

EduOS is a white-labeled, multi-tenant SaaS: one codebase, many institutions, each on its own subdomain with its own branding. Identity is therefore **siloed per tenant** — this is intentional, not a limitation.

### How identity is scoped
- Every `accounts.User` row belongs to exactly **one tenant** (`User.tenant` FK). There is no platform-level "global person."
- **All login is tenant-scoped.** The login page resolves the tenant from the subdomain (`organizations.tenant-config`), and every authentication carries a `tenant_id`. A user can only authenticate against the tenant whose URL they're on.
- **Identifier uniqueness is per-tenant, never global:**
  - `custom_login_id` → `unique_custom_login_id_per_tenant`
  - `email` → `unique_email_per_tenant_role` (unique per *(tenant, role)*; was previously global-unique). Per-role rather than per-tenant so one person holding two roles in the same school — linked via `linked_user_group_id` — can share an email across those rows, while two distinct same-role users still cannot collide.
  - `phone` → not unique at all (deliberate; shared/guardian phones and cross-tenant reuse are expected).

### Two different "multiple roles" situations
1. **Same person, two roles, SAME school** → two `User` rows in the *same* tenant, joined by a shared `linked_user_group_id`. Auto-linked at invite time via `get_users_by_phone_in_tenant` (EC-AUTH-13). Disambiguation only needed when both roles log in by phone (admin + parent, EC-AUTH-11).
2. **Same person, roles in DIFFERENT schools** (e.g. parent at School A, faculty at School B) → two fully **independent** `User` rows in **different tenants**, with **no link**. `linked_user_group_id` is tenant-local and never spans tenants. Each account has its own identifier, password, and JWT; she logs in separately at each school's subdomain.

### Why siloed identity is correct for white-label
Linking her two accounts into one identity would break the white-label illusion — School A's branded portal must not "know" she also works at School B. Hard tenant isolation protects privacy, prevents cross-institution data leakage, and keeps each deployment feeling like a separate product. The only trade-off is no cross-school SSO (two logins), which is expected for institutional software.

### If cross-school SSO is ever required
Add a **platform-level identity layer above tenants** (e.g. a `PlatformAccount` owning many tenant-scoped `User` rows + an org-switcher after login). This is a deliberate future product decision, is a meaningful build, and partially conflicts with white-labeling — pursue only on explicit customer demand. **Not in Phase 1 scope.**

> Verified behaviour (tests in `apps/accounts/tests/test_edge_cases.py`): the same email is allowed across tenants, and rejected as a duplicate within a single tenant.
