# Stage 5 — Admissions & Enrollment: Detailed Implementation Plan

> Same discipline as Stages 1–4: per-entity models, **all ORM in `queries/`**, thin views
> → interactors (`@transaction.atomic`) → queries, camelCase serializers, optimistic
> `version`, integer paise for money. This is the stage where the **enrollment seam** that
> Attendance, Fees, and Examinations were built against finally gets a real
> `StudentEnrollment` record.

---

## 0. Current state of the app

`apps/admissions/` is a **registered but empty skeleton** — in `INSTALLED_APPS`
(`base.py:65`) and `config/urls.py` (`api/v1/admissions/`). Directory tree exists
(models `application.py`/`enrollment.py`; interactors `application`, `enquiry`,
`enrollment`, `merit_list`, `duplicate_detection`; queries `application`/`enquiry`/
`enrollment`; views `application`/`enquiry`/`enrollment`/`waitlist`), but **every file is a
stub** (0 queries, 0 interactors, 0 tests; only ~34 LOC of model stubs). Greenfield.

---

## 1. Goal & scope

Deliver the full admissions funnel and the enrollment record that anchors the rest of the
system:

1. **Enquiry capture** (F-071) — source-tagged (walk-in / social / referral / online).
2. **Application pipeline** (F-072) — Enquiry → Application → Document Upload →
   Verification → Enrollment, with resumable wizard state (EC-FORM-02).
3. **Documents** (F-079) — upload + verification status (S3 key now stubbed, presign later).
4. **Merit list** (F-075) and **waitlist** (F-084) — ranked, with promote-to-application.
5. **Duplicate detection** (F-080 / EC-DATA-03 / EC-GUARD-06) — name + DOB + phone at
   enrollment → 409 with conflict summary; admin override (twin/sibling).
6. **Enrollment provisioning** (F-081) — create student `User` + `StudentProfile` +
   **`StudentEnrollment`**; invite/link parent (linked-account warning per EC-FORM-09);
   assign fee-structure snapshot (F-082); assign `custom_login_id` / admission number.
7. **Rejection** (F-083) and **transfer admission** (F-085 / EC-XFER) — link archived prior
   branch records.
8. **Funnel analytics** (F-078) — conversion by stage and source.

**Out of scope (later):** real S3/CloudFront presign (Operations stage — we store a key),
real Celery saga + Redis lock (we use a synchronous `@transaction.atomic` provisioning with
a `JobRun`-shaped result and leave the saga seam), MFA enrollment (Auth stage), the
academic-year rollover engine itself (Stage 6 — but Stage 5 must make `StudentEnrollment`
rollover-ready: `backlog_subjects`, `is_transferred`, per-year uniqueness).

---

## 2. The enrollment seam — the central decision (read first)

Attendance, Fees, and Examinations all FK **`accounts.StudentProfile`** today, each marked
`# ENROLLMENT SEAM`. The PRD's target data model FKs **`StudentEnrollment`**
(`student_enrollment_id`) on `AttendanceRecord`, `FeeInvoice`, `ExamRegistration`,
`MarksEntry`, etc. Two ways to land this:

**Option A — Full FK migration now (PRD-literal).** Swap ~10 FKs in 3 tested modules from
`StudentProfile` → `StudentEnrollment`, write data migrations to backfill, and update every
query + test. *Pros:* matches PRD exactly. *Cons:* high blast radius — rewrites stable,
143-test-green modules; data migration must invent enrollments for existing seed rows; large
diff with real regression risk.

**Option B — `StudentEnrollment` as system-of-record, profile FK retained (recommended).**
Make `StudentEnrollment` the canonical per-(student, academic_year) record that owns batch,
fee-structure snapshot, transfer lineage, and `backlog_subjects`. Because there is exactly
**one active enrollment per student per year**, the existing downstream `StudentProfile`
FKs remain functionally correct (profile ↔ active-year enrollment is 1:1). Provisioning
creates the profile *and* its enrollment together; `StudentProfile.current_batch` becomes a
**synced mirror** of `current_enrollment.batch`. Add `StudentProfile.current_enrollment` (FK,
null) so any module can resolve the enrollment in one hop. *Pros:* zero rewrite of
Attendance/Fees/Exams, no risky backfill, keeps 185 tests green. *Cons:* the literal
`student_enrollment_id` FK swap is deferred to a documented future migration (Stage 6+,
once rollover produces multiple enrollments per student and the 1:1 assumption ends).

> **Recommendation: Option B for Phase 1.** It satisfies the data-model *intent*
> (enrollment is the anchor record carrying year/batch/snapshot/backlog/transfer) without
> destabilizing three shipped modules. The FK literal swap becomes a clean, isolated Stage-6
> migration when rollover actually creates a second enrollment row per student. **This is
> open-decision OD-1 below — confirm before building 5.0.**

---

## 3. Critical dependencies & decisions

| # | Decision | Resolution |
|---|----------|-----------|
| D1 | Enrollment anchor | `StudentEnrollment` (branch, student_profile, batch, academic_year, fee_structure_snapshot, is_transferred, transferred_from_branch, backlog_subjects JSONB, status). Unique `(student_profile, academic_year)` and index `(batch, academic_year)`. |
| D2 | Provisioning creates accounts | Reuse `accounts` queries to create the student `User` (role=student, `custom_login_id`=admission number) + `StudentProfile`; never touch `accounts` `.objects` directly. |
| D3 | Parent linking | Reuse `accounts` `StudentGuardianLink` + `linked_user_group_id`. If parent phone/email matches an existing same-tenant user → **warning + explicit confirm** (F-081 / EC-FORM-09), never silent create. Exactly one `is_primary_contact` (F-288). |
| D4 | Fee snapshot at enrollment | On enroll, call `fees.queries` to create the `StudentFeeAssignment` with the structure snapshot frozen (F-082 / F-150 / EC-FEE-06). Reuses Stage 3. |
| D5 | Admission-number / custom_login_id uniqueness | Unique per tenant (EC-AUTH-24 → 400 "Roll Number already in use"). Student can't log in until ID assigned (EC-AUTH-27 → invite SMS withheld). |
| D6 | Duplicate detection | `name + DOB + phone` match → 409 `possible_duplicate` with conflict summary (F-080 / EC-DATA-03). Admin override with reason sets `sibling_group_id` for twins (EC-GUARD-06). |
| D7 | Plan student limit | Enrollment respects tenant `TenantQuota` — N+1 → 403 `limit_reached` (EC-TEN-06). Reuse `organizations.queries`. |
| D8 | Provisioning atomicity | One `@transaction.atomic` interactor returning a `JobRun`-shaped result; payment against an unfinished enrollment → 409 `enrollment_not_ready` seam (EC-CONCUR-03). Bulk commit catches `DeadlockDetected`, retries 3× (EC-CONCUR-05). |
| D9 | Transfer | New enrollment at Branch B; Branch A enrollment archived (`is_active=False`), `is_transferred=True`, `transferred_from_branch` set; edits at A → 403 (EC-XFER-02). |
| D10 | Wizard resume | `Application.step` JSONB holds resume state; abandon at step 3 → resume at step 3 (EC-FORM-02). |

---

## 4. Models (`apps/admissions/models/`)

All extend `core.BaseModel`. Branch-scoped.

### 4.1 Enums (`enums.py`)
`EnquirySource` (walk_in / social / referral / online) · `EnquiryStatus`
(new / contacted / converted / lost) · `ApplicationStatus`
(draft / submitted / under_review / accepted / rejected / waitlisted / enrolled) ·
`DocVerificationStatus` (pending / verified / rejected) · `EnrollmentStatus`
(active / transferred / graduated / withdrawn) · `GuardianRelationship` reused from accounts.

### 4.2 `application.py`
- **`Enquiry`** (F-071) — `branch`, `source`, `course` (FK, null), `applicant_name`, `dob`,
  `phone`, `email`, `status`, `captured_by` (FK User). Index `(branch, status, created_at)`.
- **`Application`** (F-072) — `enquiry` (1:1), `course`, `step` JSONB (resume state, D10),
  `eligibility_result` JSONB, `status`, `version`. Index `(branch, status, course)`.
- **`ApplicationDocument`** (F-079) — `application`, `doc_type`, `s3_key`,
  `verification_status`, `verified_by`. 1 application → N documents.
- **`Waitlist`** (F-084) — `application`, `course`, `rank`, ranked; promote action moves to
  application pipeline.

### 4.3 `enrollment.py`
- **`StudentEnrollment`** (D1) — the anchor. `branch`, `student_profile` (FK accounts),
  `batch` (FK academics), `academic_year` (FK academics), `application` (FK, null for
  direct/seed), `fee_structure_snapshot` (FK fees, null), `is_transferred`,
  `transferred_from_branch` (FK, null), `backlog_subjects` JSONB (college, EC-ROL-05),
  `sibling_group_id` (UUID, null, EC-GUARD-06), `status`. **Unique
  `(student_profile, academic_year)`**; index `(batch, academic_year)`,
  `(student_profile, is_active)`.

> Add to `accounts.StudentProfile` (Option B): `current_enrollment` FK (null) + keep
> `current_batch` as a mirror synced on provisioning/transfer. One named place to migrate
> downstream FKs later.

---

## 5. Enrollment provisioning (Flow — F-081/F-082, the heart)

`ProvisionEnrollmentInteractor.execute()` — single `@transaction.atomic`:

1. **Duplicate check** (D6) — `name+DOB+phone`; if match and no override → 409
   `possible_duplicate`. Override with reason → set `sibling_group_id`.
2. **Quota check** (D7) — `organizations.queries` active-student count vs `TenantQuota`;
   N+1 → 403 `limit_reached`.
3. **Account creation** (D2) — `accounts.queries` create student `User`
   (`custom_login_id`=admission number, unique-per-tenant → EC-AUTH-24) + `StudentProfile`.
4. **Parent link** (D3) — match existing same-tenant user by phone/email → if found, require
   `confirmLinked=true` (else return warning payload, EC-FORM-09); create/link
   `StudentGuardianLink` with one `is_primary_contact` (F-288).
5. **Enrollment record** — create `StudentEnrollment` (batch, year, snapshot ref); set
   `profile.current_enrollment` + `current_batch`.
6. **Fee snapshot** (D4) — `fees.queries` create `StudentFeeAssignment` frozen at enroll.
7. **Invite** — withhold SMS until `custom_login_id` assigned (EC-AUTH-27).
8. Return a `JobRun`-shaped result `{status: completed, steps: […]}`; mid-provision payment
   → 409 `enrollment_not_ready` (EC-CONCUR-03 seam).

All steps call **other apps' query layers** (accounts, organizations, fees, academics) —
never their `.objects`.

---

## 6. Endpoint surface (`/api/v1/admissions/`)

**Enquiries** `POST/GET/PATCH enquiries/` · `POST enquiries/{id}/convert/` (→ application)
**Applications** `POST/GET/PATCH applications/` · `PATCH applications/{id}/step/` (wizard save) ·
`POST applications/{id}/documents/` · `PATCH documents/{id}/verify/` ·
`POST applications/{id}/reject/` (F-083) ·
`POST applications/{id}/enroll/` (provisioning, §5)
**Merit / waitlist** `POST courses/{id}/merit-list/` (F-075) · `GET/POST waitlist/` ·
`POST waitlist/{id}/promote/` (F-084)
**Enrollment / transfer** `GET enrollments/` · `POST enrollments/transfer/` (F-085/EC-XFER) ·
`GET enrollments/{id}/`
**Analytics** `GET funnel/` (F-078 — conversion by stage + source)
**Bulk** `POST enrollments/bulk/` (CSV; shared-guardian dedupe EC-AUTH-28; warning rows
EC-FORM-09; deadlock retry EC-CONCUR-05)

---

## 7. Edge cases — where each is enforced

| Code | Rule | Enforced in |
|------|------|-------------|
| F-080 / EC-DATA-03 | Duplicate name+DOB+phone → 409 | duplicate_detection interactor |
| EC-GUARD-06 | Twins → confirm + `sibling_group_id` | duplicate override path |
| EC-AUTH-24 | Duplicate admission no → 400 | accounts create query unique check |
| EC-AUTH-27 | ID not yet assigned → no login / no SMS | provisioning invite gate |
| EC-AUTH-28 | Shared guardian phone (bulk) → 1 parent, 2 links | bulk dedupe |
| EC-FORM-02 | Wizard abandon → resume | `Application.step` JSONB |
| EC-FORM-09 | Parent phone = existing faculty → warning, confirm | parent-link interactor |
| EC-TEN-06 | Plan limit exceeded → 403 `limit_reached` | quota check |
| EC-CONCUR-03 | Payment mid-provision → 409 `enrollment_not_ready` | provisioning saga status |
| EC-CONCUR-05 | Bulk deadlock → retry 3× | bulk interactor backoff |
| EC-XFER-01 | Transfer A→B → new B, archive A | transfer interactor |
| EC-XFER-02 | Edit A after transfer → 403 | enrollment views branch guard |
| EC-FEE-06 / F-150 | Structure changes post-enroll → keep snapshot | fee snapshot frozen at enroll |
| EC-ROL-05 | Arrears carried in `backlog_subjects` | enrollment model field (rollover reads in Stage 6) |
| F-288 / EC-GUARD-07 | Exactly one primary contact | guardian-link partial unique |

---

## 8. Architecture (non-negotiable)

Thin views → interactors (`@transaction.atomic`) → queries. **`.objects`/`.save()`/
`select_for_update` only in `queries/`.** Cross-app writes (accounts, fees, organizations,
academics) go through *their* query functions. Verify after every change:
`grep -rn "\.objects\.\|\.save(\|select_for_update" apps/admissions/{views,interactors,serializers}` → empty.

---

## 9. File-by-file build plan

```
models/application.py    Enquiry, Application, ApplicationDocument, Waitlist
models/enrollment.py     StudentEnrollment (+ accounts.StudentProfile.current_enrollment)
enums.py                 all TextChoices
queries/enquiry.py       enquiry CRUD, funnel aggregates
queries/application.py   application + document + waitlist CRUD, merit ranking
queries/enrollment.py    enrollment create/list, transfer, duplicate-match query
interactors/enquiry.py   capture, convert
interactors/application.py  step-save, document verify, reject
interactors/merit_list.py   ranked merit generation
interactors/duplicate_detection.py  name+DOB+phone match + override
interactors/enrollment.py   ProvisionEnrollmentInteractor (§5), TransferInteractor, bulk
serializers/*.py         camelCase in/out
views/*.py + urls.py     endpoint surface
admin.py                 register models
tests/                   one test per F / EC (below)
```

Then `makemigrations admissions accounts` (the `current_enrollment` FK touches accounts;
answer non-null prompts as in Stage 2), `migrate`, `check`, `makemigrations --check`.

---

## 10. Build order (sub-stages) & effort

| Sub-stage | Content | Effort |
|-----------|---------|--------|
| 5.0 | Confirm OD-1 (seam approach); enums + all models + `current_enrollment`; migration | M |
| 5.1 | Enquiry + Application pipeline + wizard step-save + documents (F-071/072/079, EC-FORM-02) | M |
| 5.2 | Merit list + waitlist + promote (F-075/084) | S |
| 5.3 | Duplicate detection + override/sibling (F-080, EC-DATA-03, EC-GUARD-06) | M |
| 5.4 | **Enrollment provisioning saga** — accounts + parent-link + enrollment + fee snapshot + quota + invite gate (F-081/082, EC-FORM-09/AUTH-24/27/TEN-06/CONCUR-03) | **L** |
| 5.5 | Transfer admission + archive lineage (F-085, EC-XFER-01/02) | M |
| 5.6 | Rejection + funnel analytics (F-083/078) | S |
| 5.7 | Bulk CSV enrollment (EC-AUTH-28, EC-FORM-09, EC-CONCUR-05) | M |
| 5.8 | Full test pass + queries-rule scan + migration check; confirm 185 baseline stays green | M |

Provisioning (5.4) is the heavy substage — it composes accounts, organizations, fees, and
academics through their query layers in one transaction.

---

## 11. Testing plan

`env` fixture (tenant + quota + branch + year + course + batch + fee structure + admin).
Happy path: enquiry → application → docs verified → enroll → assert student User +
StudentProfile + StudentEnrollment + fee assignment all created and linked. Then one test
per row in §7. Plus school-vs-college (backlog only college). Keep the existing **185
green**; add admissions tests with **zero** ORM-outside-queries violations.

Command (unchanged):
```
export PATH="$HOME/.local/bin:$PATH" && unset USE_POSTGRES DATABASE_URL && \
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest -p no:cacheprovider -q
```

---

## 12. Open decisions (confirm before building)

- **OD-1 (must confirm before 5.0): enrollment seam approach** — Option A (full FK
  migration of Attendance/Fees/Exams now) vs **Option B (recommended:** `StudentEnrollment`
  as system-of-record, downstream profile FKs retained, literal FK swap deferred to Stage 6).
- **OD-2: provisioning sync vs async** — synchronous `@transaction.atomic` returning a
  `JobRun`-shaped result now (recommended), or real Celery saga (defer to Operations).
- **OD-3: documents** — store S3 key stub now, or wire presigned upload here (recommended:
  stub key now, presign in Operations).
- **OD-4: bulk CSV** — include in Phase-1 Stage 5 (5.7) or defer; it carries the trickiest
  dedupe edge cases (EC-AUTH-28 / EC-FORM-09).

---

## 13. Risks

- **The seam (OD-1)** is the dominant risk. Option B keeps blast radius near zero; Option A
  rewrites three shipped modules — do not start until OD-1 is confirmed.
- **Provisioning composition** — touches four other apps; a single stray `.objects` breaks
  the architecture rule. Everything routes through query layers.
- **Parent-link correctness** — linked-account warning (EC-FORM-09) and single-primary-
  contact (F-288) are subtle; tests must assert the *warning-then-confirm* flow, not just
  the happy path.
- **Quota / limit** coupling with billing — `limit_reached` (EC-TEN-06) must read the same
  `TenantQuota` the per-student billing model uses, so seat counts stay consistent.
```
