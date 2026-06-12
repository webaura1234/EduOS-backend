# Stage 4 — Examinations, Marks & Results: Detailed Implementation Plan

> Same discipline as Stage 2 (Attendance) and Stage 3 (Fees): models split per-entity,
> **all ORM in `queries/`**, thin views → interactors (`@transaction.atomic`) → queries,
> camelCase serializers matching `@eduos/types`, integer money in paise, optimistic
> `version` on anything two users edit concurrently. Write the plan first, build second.

---

## 0. CRITICAL — current state of the app

`apps/examinations/` is a **registered but empty skeleton**. It is already in
`INSTALLED_APPS` (`config/settings/base.py:67`) and wired into `config/urls.py`
(`api/v1/examinations/`), and the directory tree exists (models/queries/interactors/
serializers/views/tests, plus `enums.py`, `constants.py`, `filters.py`, `permissions.py`,
`signals.py`, `tasks.py`). **Every file is a TODO stub — 0 models, 0 queries, 0 tests.**
So Stage 4 is greenfield. The stub `models/__init__.py` already names the intended models
(`GradeScale, Exam, ExamSchedule, ExamRegistration, HallTicket, Seating, MarksEntry,
Result, Assignment`) — this plan refines that into the final model set.

This is the **most logic-heavy module after Fees**: it owns mark validation, deadline
enforcement, concurrent-edit guards, a two-step publish with snapshot hashing, GPA/grade
computation that diverges by institution type, and PDF artifacts (hall ticket, report
card, transcript).

---

## 1. Goal & scope

Deliver the full examination lifecycle for **Phase 1**:

1. **Exam setup** — grade scales, exams, per-subject schedule slots (room + time), with
   clash detection and holiday warnings.
2. **Registration & exam-fee gate** — students registered for an exam; hall ticket blocked
   until the linked exam-fee invoice is paid (reuses Stage 3 fees).
3. **Logistics** — hall ticket PDF, seating allocation, invigilator duty.
4. **Marks entry** — faculty enter internal + exam marks, with max/negative validation,
   hard deadline (admin override audited), absent handling, optimistic concurrency,
   conflict-of-interest guard.
5. **Results** — two-step publish with snapshot hash + immutable revision history;
   computed grade/GPA per the course grade scale; **school → report card**,
   **college → marksheet/transcript with CGPA/SGPA + arrears + grace marks**.
6. **Assignments** — create/assign/submit/grade with a plagiarism-similarity field.
7. **Student/parent hubs** — exam schedule, hall ticket, exam fee, published results,
   assignment status.

**Out of scope (later stages):** real S3/CloudFront upload pipeline (F-300/F-301 — we
generate PDF bytes and stash a key; the presign service lands with Operations), real Redis
publish lock + WebSocket fan-out (we use a DB row-lock equivalent and leave a documented
seam), and `StudentEnrollment`/admissions (Stage 5 — see the enrollment seam below).

---

## 2. Critical dependencies & decisions

| # | Decision | Resolution |
|---|----------|-----------|
| D1 | **Enrollment seam** — PRD keys exam rows off `StudentEnrollment`, which is Stage 5. | Key `ExamRegistration` / `MarksEntry` off **`accounts.StudentProfile`** (`current_batch`), exactly like Attendance and Fees already do. One documented FK (`student = FK StudentProfile`). Add a `# ENROLLMENT SEAM` comment; Stage 5 migrates these to `StudentEnrollment` in one place. |
| D2 | **Room / hall** for scheduling + seating. | Reuse the existing **`academics.Room`** model (already built for "timetable and exam scheduling", `db_table=academics_room`). No new room model. |
| D3 | **Exam fee** integration. | Reuse Stage 3 fees. `create_invoice(...)` already accepts a null `assignment`, so an exam-fee invoice is created with `assignment=None`, a single line, due date. `ExamRegistration.fee_invoice` FKs it. Hall-ticket gate checks `invoice.status == PAID`. |
| D4 | **School vs college divergence**. | Branch via `tenant.institution.is_school` / `is_college`. School: term report card, letter grades, no GPA/credits/arrears, no grace marks. College: marksheet/transcript, SGPA/CGPA from credits, arrear tracking, grace marks (F-050/F-128, **college-only**, EC-EXAM-07 returns 403 for school). |
| D5 | **Marks precision**. | Marks are `DecimalField(max_digits=6, decimal_places=2, null=True)` — *not* paise. Null = absent (EC-EXAM-04). GPA/percentage math uses `Decimal` + banker's rounding (`ROUND_HALF_EVEN`), reusing the rounding helper pattern from `fees/helpers/paise.py`. |
| D6 | **Publish concurrency** (EC-CONCUR-01). | Phase-1: a `select_for_update()` lock on the `Exam` row + a unique partial constraint on "active publication per exam" inside the publish transaction gives the same guarantee as a Redis lock for a single worker. Leave a `# TODO Redis lock` seam. Return 409 `job_in_progress` if a publication is mid-flight. |
| D7 | **Marks edit concurrency** (EC-CONCUR-02). | `BaseModel.version`. PATCH carries `version`; query does `filter(pk, version=expected)` and 0-row update → 409 with `currentVersion`/`currentValue`. |
| D8 | **PDF artifacts**. | Generate bytes server-side (reportlab) in a `services/pdf.py` layer; persist a `file_key` + size on the row. Actual presigned download (F-301) is stubbed to a local key now, swapped in Operations stage. |
| D9 | **Subject archive guard** (F-096 / EC-DATA-02). | A subject with any `MarksEntry` cannot be deleted — only archived (`is_active=False`). Enforced in the academics delete path via a new `examinations.queries` count helper (academics imports examinations query, not its ORM). |

---

## 3. Models (`apps/examinations/models/`)

All extend `core.BaseModel` (UUID PK, timestamps, soft-delete `is_active`, audit
`created_by`/`updated_by`, optimistic `version`). Branch-scoped where a tenant boundary
applies.

### 3.1 Enums (`enums.py`)
`ExamType` (unit / midterm / final / internal / practical / arrear) · `MarksStatus`
(`draft | submitted | locked`) · `ResultStatus` (provisional / published / revised) ·
`AssignmentStatus` (open / closed) · `SubmissionStatus` (submitted / late / graded) ·
`GradeBand` is data, not enum.

### 3.2 `exam.py` — setup & scheduling
- **`GradeScale`** (F-128/F-050 college, F-131 school) — `branch`, `course` (FK, scale is
  per-course per D4), `name`, `bands` JSONB (`[{min_percent, max_percent, grade, grade_point}]`),
  `grace_marks_max` (int, college-only), `is_default`.
- **`Exam`** (F-116) — `branch`, `academic_period` (FK academics), `name`, `exam_type`,
  `is_published` (denormalized convenience), `result_status`. An exam groups schedule slots.
- **`ExamScheduleSlot`** (F-116/F-134) — `exam`, `subject` (FK academics), `batch` (FK),
  `room` (FK `academics.Room`), `start_at`, `end_at`, `max_capacity`, `max_marks`
  (snapshot from subject, overridable). **Clash detection** (EC-EXAM-06/F-134) →
  no overlapping `(room, [start,end])`; holiday warning (EC-TT-03/F-133) is a soft 200 with
  `warnings[]` unless `override=true`.
- **`InvigilatorDuty`** (F-119) — `schedule_slot`, `faculty` (FK User), unique
  `(slot, faculty)`.

### 3.3 `results.py` — registration, logistics, marks, results
- **`ExamRegistration`** (F-118/F-127/F-152) — `exam`, `student` (StudentProfile, **D1**),
  `fee_invoice` (FK `fees.FeeInvoice`, null), `fee_paid` (bool, derived), `is_arrear`
  (college, F-049/F-129), unique `(exam, student)`.
- **`HallTicket`** (F-117/F-047) — `registration` (1:1), `file_key`, `roll_number`,
  `regulation` (college), `generated_at`. Generation **blocked** if `fee_paid` is false
  (EC-EXAM-01 → 403 `exam_fee_unpaid`).
- **`Seating`** (F-118/EC-EXAM-05) — `schedule_slot`, `student`, `room`, `seat_number`,
  unique `(slot, room, seat_number)` (EC-CONCUR-04). Odd counts → last room partial fill.
- **`MarksEntry`** (F-120/F-121/F-188) — `exam`, `subject`, `student` (**D1**),
  `marks` (Decimal, **null = absent**), `is_absent`, `is_internal`, `marks_status`,
  `grace_applied` (Decimal default 0), `submitted_at`, `version`. **Unique
  `(exam, subject, student)`**.
- **`ResultPublication`** (F-122/EC-EXAM-02 — two-step publish) — `exam`, `published_at`,
  `published_by`, `snapshot_hash` (sha256 of frozen marks set), `is_revised`, `revision_no`,
  `parent_publication` (FK self, null).
- **`ResultRevisionHistory`** (F-123, immutable, EC-EXAM-03) — append-only log of every
  change after first publish; published results are marked revised, **never deleted**.
- **`StudentResult`** (F-131/F-132/F-202) — computed per `(exam, student)`: `total_marks`,
  `percentage`, `grade`, `gpa` (college), `is_pass`, `arrear_subjects` JSONB (college),
  `report_card_key` / `marksheet_key`.

### 3.4 `assignment.py` — coursework (F-126/F-219)
- **`Assignment`** — `branch`, `batch_subject` (FK academics), `title`, `description`,
  `max_marks`, `due_at`, `status`, `created_by` (faculty).
- **`AssignmentSubmission`** — `assignment`, `student` (**D1**), `file_key`,
  `plagiarism_score` (Decimal, null — indicator only, F-126), `graded_marks` (null until
  graded), `submission_status`, `version`. Unique `(assignment, student)`.

### 3.5 College-only (built behind D4 gate, kept minimal for Phase 1)
`arrear_subjects` lives on `StudentResult` (JSONB) and `ExamRegistration.is_arrear`
covers F-049/F-129; a separate `StudentGPA` aggregate (CGPA across periods) is computed on
read from `StudentResult` rows rather than stored, to avoid a stale denormalization
(recompute job EC-CEL-06 reads only `marks_status=submitted/locked`).

---

## 4. Exam-fee gate (integration with Stage 3 fees) — Flow / F-127/F-152/EC-EXAM-01

1. Admin sets an exam fee amount on the `Exam` (or per registration batch).
2. On registration, `examinations.interactors.registration` calls
   `fees.queries.invoice.create_invoice(branch, student, assignment=None, total_paise=…)`
   inside the same transaction and stores `fee_invoice`.
3. Student pays via the **existing** Stage 3 capture flow (Razorpay sandbox or offline
   → platform/admin approval). No new payment code.
4. `HallTicket` generation interactor checks `fee_invoice.status == PAID`
   (via `fees.queries.invoice.get_invoice_by_id`); else **403 `exam_fee_unpaid`**.

> examinations **calls fees query functions** — it never touches `fees` models' `.objects`.

---

## 5. Endpoint surface (`/api/v1/examinations/`)

**Admin — setup**
`POST/GET/PATCH grade-scales/` · `POST/GET/PATCH exams/` ·
`POST/GET/PATCH exams/{id}/schedule/` (clash + holiday warning) ·
`POST exams/{id}/invigilators/`

**Admin — registration & logistics**
`POST exams/{id}/register/` (bulk batch register → creates exam-fee invoices) ·
`POST exams/{id}/seating/generate/` (EC-EXAM-05) ·
`GET registrations/{id}/hall-ticket/` (EC-EXAM-01 gate, returns PDF/signed key)

**Faculty — marks (F-120/F-121/F-188/F-253)**
`GET schedule-slots/{id}/roster/` · `POST schedule-slots/{id}/marks/` (bulk draft) ·
`PATCH marks/{id}/` (version-checked, EC-CONCUR-02) ·
`POST schedule-slots/{id}/marks/submit/` (locks; **deadline** → 403 faculty / admin override audited, EC-FORM-05)

**Admin — results (F-130/F-128)**
`POST exams/{id}/results/compute/` · `POST exams/{id}/results/publish/` (two-step:
needs `confirmToken`, EC-EXAM-02; lock → 409, EC-CONCUR-01) ·
`POST exams/{id}/results/revise/` (EC-EXAM-03 — revise, never delete) ·
`POST exams/{id}/grace-marks/` (college-only, EC-EXAM-07 → 403 school) ·
`GET exams/{id}/analytics/` (F-124/F-039 — pass %, toppers, subject-wise breakdown)

**Assignments (F-126/F-219)**
`POST/GET assignments/` · `POST assignments/{id}/submit/` (student) ·
`PATCH submissions/{id}/grade/` (faculty)

**Student / parent hubs (F-135/F-196/F-200–F-203/F-211/F-219)**
`GET me/exams/` (schedule + fee + hall-ticket state) · `GET me/results/` ·
`GET me/assignments/` · parent variants scoped to linked child (read-only).

---

## 6. Edge cases — where each is enforced

| Code | Rule | Enforced in |
|------|------|-------------|
| EC-EXAM-01 | Hall ticket, unpaid exam fee → 403 `exam_fee_unpaid` | `hall_ticket` interactor, fee-status check |
| EC-EXAM-02 | Publish without confirm token → 400 two-step | `result` interactor (`confirmToken`) |
| EC-EXAM-03 | Delete published result → 403, revise only | `result` views/interactor; `ResultRevisionHistory` |
| EC-EXAM-04 | Absent → DB null, display `AB`, GPA exclude per config | `MarksEntry.is_absent` + serializer + GPA calc |
| EC-EXAM-05 | Seating odd count → last room partial fill | `seating` interactor allocation loop |
| EC-EXAM-06 | Two exams same hall slot → 400 clash | `exam` schedule query (overlap check) |
| EC-EXAM-07 | Grace marks on school → 403 college-only | `grace` interactor + `is_college` gate |
| EC-FORM-05 | Marks after deadline → 403 faculty / 200 admin+audit | `marks` submit interactor |
| EC-FORM-06 / F-252 | Marks > max or negative → 400 | `marks` serializer validation |
| EC-CONCUR-01 | Two publishers → 409 `job_in_progress` | `select_for_update` on Exam + partial unique |
| EC-CONCUR-02 | Concurrent marks PATCH → 409 `currentVersion` | version-checked update query |
| EC-CONCUR-04 | Two clients claim same seat → DB unique rejects | `(slot, room, seat_number)` unique |
| EC-CEL-06 | CGPA recompute mid-entry → reads only submitted | GPA query filters `marks_status in (submitted, locked)` |
| EC-DATA-02 / F-096 | Delete subject with marks → archive only | `examinations.queries.marks.count_for_subject` used by academics |
| EC-TT-03 / F-133 | Exam on holiday → warning + override | schedule interactor soft-warning |
| EC-GUARD-02 / F-290 | Faculty marks own child → hard block + override | `marks` interactor conflict check (`linked_user_group_id`) |
| EC-ROL-05 | Arrear rollover keeps original ExamRegistration | (Stage 5 rollover reads these; we keep `is_arrear` + leave records intact) |

---

## 7. Architecture (non-negotiable, same as Stages 1–3)

- **Views** thin: parse via camelCase serializer → call interactor → serialize out. No ORM.
- **Interactors** own business logic, wrapped in `@transaction.atomic`; call **query
  functions** only.
- **Queries** are the *only* place `.objects` / `.save()` / `select_for_update()` appears.
- Cross-app reads go through the **other app's query layer** (fees, academics, accounts) —
  never their `.objects`.
- Verify after every change: `grep -rn "\.objects\.\|\.save(\|select_for_update" apps/examinations/{views,interactors,serializers}` must be **empty**.

---

## 8. File-by-file build plan

```
models/exam.py          GradeScale, Exam, ExamScheduleSlot, InvigilatorDuty
models/results.py       ExamRegistration, HallTicket, Seating, MarksEntry,
                        ResultPublication, ResultRevisionHistory, StudentResult
models/assignment.py    Assignment, AssignmentSubmission
enums.py                all TextChoices
queries/exam.py         scale/exam/slot CRUD, clash + holiday overlap, invigilator
queries/marks.py        roster, bulk upsert, version-checked update, count_for_subject,
                        submitted-only reads (EC-CEL-06)
queries/result.py       publication create+lock, revision append, student-result upsert
queries/registration.py register, fee-invoice link, hall ticket, seating
services/pdf.py         hall_ticket / report_card / transcript byte generation
services/grading.py     percentage, grade-band lookup, SGPA/CGPA, grace application
interactors/*.py        exam, marks, result, hall_ticket, seating, gpa, assignment
serializers/*.py        camelCase in/out
views/*.py + urls.py    endpoint surface
admin.py                register models
tests/                  one test per F / EC (below)
```

Then: `makemigrations examinations` (answer any interactive default prompts for the
non-null FKs on existing data the same way Stage 2 did), `migrate`, `check`,
`makemigrations --check`.

---

## 9. Testing plan (every F / EC gets a test)

Mirror `attendance/tests/test_attendance_api.py` style: a single `env` fixture
(tenant + branch + academic year/period + course + batch + subjects + room + admin +
faculty + 2 students with profiles), helper `_client(user)`, then:

- Happy path: setup exam → schedule → register → pay (sandbox) → hall ticket → enter marks
  → submit → compute → publish → read result.
- One test per row in §6 (EC-EXAM-01..07, EC-FORM-05/06, EC-CONCUR-01/02/04, EC-CEL-06,
  EC-DATA-02, EC-TT-03, EC-GUARD-02).
- School vs college divergence: grade letters vs SGPA/CGPA; grace-marks 403 on school.
- Run full suite — must keep the existing **143 green** and add the examinations tests on
  top with **zero** ORM-outside-queries violations.

Test command (unchanged):
```
export PATH="$HOME/.local/bin:$PATH" && unset USE_POSTGRES DATABASE_URL && \
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest -p no:cacheprovider -q
```

---

## 10. Build order (sub-stages) & effort

| Sub-stage | Content | Rel. effort |
|-----------|---------|-------------|
| 4.0 | Enums + all models + migration + admin | M |
| 4.1 | Exam/scale/schedule CRUD + clash + holiday warning (F-116/133/134, EC-EXAM-06) | M |
| 4.2 | Registration + exam-fee invoice link + hall ticket gate (F-118/127/152, EC-EXAM-01) | M |
| 4.3 | Seating + invigilator (F-118/119, EC-EXAM-05, EC-CONCUR-04) | S |
| 4.4 | Marks entry: validation, deadline, version, conflict-of-interest (F-120/121/252/253, EC-FORM-05/06, EC-CONCUR-02, EC-GUARD-02) | **L** |
| 4.5 | Results: compute → two-step publish → revise; grade/GPA; school report card vs college transcript; grace marks (F-128/130/131/132, EC-EXAM-02/03/04/07, EC-CONCUR-01, EC-CEL-06) | **L** |
| 4.6 | Assignments + submissions + grading (F-126/219) | M |
| 4.7 | Student/parent hubs (F-135/196/200–203/211/219) | S |
| 4.8 | Subject archive guard wired into academics (F-096/EC-DATA-02) | S |
| 4.9 | Full test pass + queries-rule scan + migration check | M |

The marks (4.4) and results (4.5) sub-stages carry the real complexity — concurrency,
deadline/override audit, conflict-of-interest, two-step publish + snapshot hash, and the
school/college branch in grading.

---

## 11. Open decisions (confirm before/while building)

1. **Exam fee scope** — one flat exam fee per Exam, or per-subject? (Plan assumes per-Exam;
   easy to extend.)
2. **Grade scale source** — per-course (plan) vs per-branch default with per-course
   override? (Plan: per-course with an `is_default` branch fallback.)
3. **PDF now or stub** — generate real reportlab bytes in 4.2/4.5, or stub the key and defer
   PDF rendering to the Operations stage with S3/CloudFront? (Plan: generate bytes now,
   local key; swap to presigned later.)
4. **GPA storage** — compute-on-read (plan) vs stored `StudentGPA` denormalization with the
   EC-CEL-06 recompute job. (Plan: compute-on-read for Phase 1; add the job if reports get
   heavy.)

---

## 12. Risks

- **Concurrency correctness** (publish lock, marks version, seat uniqueness) is the area
  most likely to be built loosely by an AI tool — tests EC-CONCUR-01/02/04 are the guard.
- **School/college branching** doubles the result paths; keep it behind the `is_college`
  gate in one `services/grading.py` so views stay identical.
- **Enrollment seam (D1)** — every exam row keys off `StudentProfile`; keep the FK in one
  named spot so the Stage 5 migration to `StudentEnrollment` is mechanical.
- **Cross-app boundary** — examinations must reach fees/academics/accounts *only* through
  their query layers; a single stray `.objects` breaks the architecture rule and the scan.
```
