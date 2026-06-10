# Stage 2 — Attendance: Detailed Implementation Plan

> **Status:** PLAN ONLY — no code yet. Reviewed against `features.md` (F-101–F-115, F-183, F-197, F-213), `edge_cases.md` (EC-ATT-01–06), `data_models.md` §6, and the frontend `packages/types/src/admin/attendance.ts` contract.

---

## 1. Goal & Scope

Build the **attendance domain** end-to-end so the Admin **Attendance** module works and the admin **Dashboard** gets live data. Concretely: faculty mark attendance per class session; admin sees a live board, runs shortage/detention reports, handles a leave queue, makes audited retroactive corrections; students/parents see their attendance %.

**In scope (Phase 1):**
- Models: `AttendanceSession`, `AttendanceRecord`, `LeaveRequest`, `AttendanceAudit`
- Marking (faculty), live board (admin), reports (admin), leave workflow (all roles), corrections (admin), student/parent read views
- Edge cases EC-ATT-01..06

**Out of scope (deferred, with hooks left):**
- Geo-fence *enforcement* with real coordinates → we store geo + a `flagged` status, but radius config is a stub (F-103 partial)
- Real WebSockets → live board is a **polling** endpoint (frontend already mocks WS via polling)
- True table partitioning → note it in model docstrings; not needed at Phase-1 scale (SQLite/dev). Add in prod migration.
- SMS absence alerts (F-112/F-216) → emit via the existing `sms.py`/Celery hook, but full comms is Stage 7

---

## 2. Critical Dependency Decision — student identity

**Problem:** PRD `AttendanceRecord.student_enrollment_id` → but `StudentEnrollment` is built in **Stage 5 (Admissions)**, which doesn't exist yet.

**Decision:** key attendance off **`accounts.StudentProfile`** (it already has `current_batch` → `academics.Batch`). Every attendance read/write resolves students via `StudentProfile.current_batch`.

- `AttendanceRecord.student` → FK to `accounts.User` (role=student) **or** `StudentProfile`. → **Use `StudentProfile`** (one row per student, carries batch + academic_status).
- Add a nullable `student_enrollment` FK placeholder = **NO** — keep it clean; when Stage 5 lands, add `enrollment` FK in a migration and backfill. Document this in the model.

**Consequence:** "who is in this class" = `StudentProfile.objects.filter(current_batch=..., academic_status=active)`. This is the seam to revisit at Stage 5.

---

## 3. Data Models (`apps/attendance/models/`)

Split per the established pattern: `enums.py`, `models/session.py`, `models/record.py`, `models/leave.py`, `models/audit.py`, wire `models/__init__.py`. All inherit `core.BaseModel` (UUID, timestamps, soft-delete, `version`, audit FKs).

### 3.1 Enums (`enums.py`)
```
SessionStatus     = scheduled | in_progress | completed | cancelled
AttendanceStatus  = present | absent | late | flagged | excused | leave
LeaveApplicantRole= student | staff
LeaveStatus       = pending | approved | rejected | cancelled
AuditType         = retroactive_edit | late_marking | geo_fence_failure
```
> Note: frontend `AttendanceStatus` uses `leave` (not `flagged`). We support **both** — `flagged` (geo-fence/needs-review, internal) and `leave` (resolved from an approved LeaveRequest). Map `flagged`→shown to admin queue; `leave` derived when a student has an approved leave covering the date.

### 3.2 `AttendanceSession` (`models/session.py`)
One class-period for which attendance is taken.
| Field | Type | Notes |
|---|---|---|
| branch | FK Branch | denormalised for fast scoping/indexing |
| batch_subject | FK academics.BatchSubject | what class |
| date | date | db_index |
| period_slot | FK academics.PeriodSlot | which slot |
| faculty | FK User (role=faculty), null | who took it |
| status | SessionStatus | default scheduled |
| **Unique** | `(batch_subject, date, period_slot)` | one session per class/slot/day (EC-ATT-06 anchor) |
**Index:** `(branch, date)`, `(faculty, date)`

### 3.3 `AttendanceRecord` (`models/record.py`)
One student's mark in a session.
| Field | Type | Notes |
|---|---|---|
| session | FK AttendanceSession | |
| student | FK accounts.StudentProfile | (enrollment seam — see §2) |
| status | AttendanceStatus | |
| geo_lat / geo_lng | Decimal, null | F-103 |
| marked_at | datetime | when actually marked |
| marked_by | FK User, null | faculty/admin |
| late_mark | bool | True if marked >2h after slot end (F-108/EC-ATT-02) |
| idempotency_key | char, UNIQUE | per `(session, student)` — EC-ATT-06 |
| **Unique** | `(session, student)` | a student appears once per session |
**Index:** `(session)`, `(student, marked_at desc)`

### 3.4 `LeaveRequest` (`models/leave.py`)
| Field | Type | Notes |
|---|---|---|
| branch | FK Branch | scoping |
| applicant_role | LeaveApplicantRole | student/staff |
| student | FK StudentProfile, null | for student leave |
| employee | FK User, null | for staff leave (HR overlaps Stage 6) |
| applied_by | FK User | who submitted (student self / parent / faculty) |
| from_date / to_date | date | |
| reason | text | |
| status | LeaveStatus | default pending |
| approver | FK User, null | |
| approved_at | datetime, null | |
| decision_note | text | reject reason |
**Index:** `(branch, status)`, `(student, from_date)`

### 3.5 `AttendanceAudit` (`models/audit.py`)
Immutable trail for F-107 (retroactive edits), F-108 (late marks), F-103 (geo-fence fails).
| Field | Type | Notes |
|---|---|---|
| record | FK AttendanceRecord | |
| audit_type | AuditType | |
| original_status / new_status | AttendanceStatus, null | EC-ATT-04 diff |
| actor | FK User | who did it |
| reason | text | |
| metadata | JSON | geo coords, original marked_at, etc. |
| created_at | datetime | append-only; never updated/deleted |

---

## 4. Endpoint Surface (`/api/v1/attendance/`)

camelCase I/O to match `admin/attendance.ts`. Permission column: `F`=faculty, `A`=admin, `SA`=super-admin, `S`=student, `P`=parent.

### Marking (faculty)
| Method | Path | Purpose | Perm | F-code / EC |
|---|---|---|---|---|
| POST | `/sessions/` | Open/get a session for batch_subject+date+slot | F | F-102 |
| GET | `/sessions/<id>/roster/` | Students in the class + current marks | F,A | F-102 |
| POST | `/sessions/<id>/mark/` | Bulk-mark records (idempotent) | F | F-102/104, EC-ATT-01/02/06 |
| PATCH | `/sessions/<id>/` | Set session status (in_progress/completed) | F,A | F-102 |

### Admin board & live
| Method | Path | Purpose | Perm | F-code |
|---|---|---|---|---|
| GET | `/live/` | Today's status across all classes (polling) | A,SA | F-101 |
| GET | `/board/?date=` | Sessions grid for a date | A,SA | F-101 |

### Reports
| Method | Path | Purpose | Perm | F-code / EC |
|---|---|---|---|---|
| GET | `/reports/shortage/?threshold=&batchId=` | Students below threshold | A,SA | F-105/114 |
| GET | `/reports/detention/` | Auto detention list | A,SA | F-115 |
| GET | `/reports/monthly/?month=&subjectId=&batchId=` | Monthly/subject report | A,SA | F-110, EC-ATT-05 |

### Leave workflow
| Method | Path | Purpose | Perm | F-code |
|---|---|---|---|---|
| POST | `/leave/` | Apply (student/parent/staff) | S,P,F | F-197/213/106 |
| GET | `/leave/?status=` | Leave queue | A,F | F-106/183 |
| PATCH | `/leave/<id>/` | Approve/reject (+note) | A,F | F-106/183 |

### Corrections (admin)
| Method | Path | Purpose | Perm | F-code / EC |
|---|---|---|---|---|
| PATCH | `/records/<id>/correct/` | Retroactive edit, writes audit | A | F-107, EC-ATT-04 |
| GET | `/audit/?type=` | Audit log (late marks, geo fails, edits) | A,SA | F-108/103 |
| GET | `/flagged/` | Geo-fence/flagged review queue | A | F-103, EC-ATT-03 |

### Student / parent read
| Method | Path | Purpose | Perm | F-code |
|---|---|---|---|---|
| GET | `/me/summary/` | Subject-wise % + history (student) | S | F-111/114 |
| GET | `/children/<studentId>/summary/` | Child attendance (parent, link-checked) | P | F-112 |

---

## 5. Core Business Logic & Edge Cases

| Rule | Where | Detail |
|---|---|---|
| **EC-ATT-01 holiday block** | mark interactor | Reject 400 if `academics.Holiday` exists for `(branch, date)` and applies to students |
| **EC-ATT-02 late mark** | mark interactor | If `now > slot.end_time + 2h` on the session date → set `late_mark=True` + write `AuditType.late_marking` |
| **EC-ATT-03 geo-fence** | mark interactor | If geo provided & outside radius (stub config) → `status=flagged` + `AuditType.geo_fence_failure`; surfaces in `/flagged/` |
| **EC-ATT-04 retroactive edit** | correct interactor | Capture `original_status` → set `new_status` → write `AuditType.retroactive_edit` (immutable diff) |
| **EC-ATT-06 idempotent sync** | mark query | `idempotency_key = f"{session_id}:{student_id}"`; upsert by unique key so replaying offline queue is safe |
| **EC-ATT-05 exam-day exclusion** | % calculator | If `TenantSettings.exam_day_counts_toward_attendance` is False, exclude sessions on exam days from denominator |
| **Frozen year** | mark/correct | Block writes if the batch's academic year `is_frozen` (reuse academics guard) |
| **Leave → status** | % calculator + roster | A student with an approved `LeaveRequest` covering the date shows as `leave`/`excused`, not `absent` |

### Attendance % calculation (the heart of reports/summary)
```
For a student over a date range / subject:
  sessions = AttendanceSession in scope (batch_subject of student's batch, status=completed)
  exclude exam-day sessions if exam_day_counts_toward_attendance = False (EC-ATT-05)
  present_like = records where status in {present, late}            (configurable: late counts?)
  excused = records where status in {excused, leave}                (removed from denominator)
  denominator = total_sessions − excused
  percent = present_like / denominator * 100
  shortage if percent < TenantSettings.attendance_threshold_percent (default 75)
```
This single helper powers F-105, F-110, F-111, F-112, F-114, F-115.

---

## 6. Architecture (follow the established rule)

```
views/      thin: validate serializer → call interactor/query → camelCase response
interactors/ business rules + @transaction.atomic (holiday block, late-mark, geo, audit, %)
queries/    ALL ORM (sessions, records, leave, audit, roster, aggregates)
serializers/ camelCase I/O matching admin/attendance.ts
permissions  reuse accounts: IsFaculty, IsAdminOrSuperAdmin, IsStudent, IsParent (+ object checks)
scoping      branch from request.user (admin) / faculty's assignments
```
**Hard rule:** no `.objects` / `.save()` outside `queries/`. Aggregations (Count/Q) live in queries; the % math lives in a pure interactor helper fed by query results.

---

## 7. File-by-file Build Plan

```
apps/attendance/
  enums.py                         (status enums)
  models/{session,record,leave,audit}.py  + __init__.py   → makemigrations
  queries/{session,record,leave,audit,report}.py
  interactors/{marking,leave,correction,report}.py
  serializers/{session,record,leave,report}.py  (camelCase)
  views/{marking,board,leave,correction,report,student}.py
  permissions.py                   (or reuse accounts)
  helpers.py                       (% calc, late-mark check, holiday check via academics query)
  urls.py                          → mount under /api/v1/attendance/ (already in config/urls.py)
  tasks.py                         (optional: SMS absence alert hook)
  tests/{test_marking,test_reports,test_leave,test_corrections,test_student_view}.py
  tests/factories.py
```

---

## 8. Testing Plan (each F/EC gets a test)
- **Marking:** open session, bulk mark, re-sync same payload → no dupes (EC-ATT-06); mark on holiday → 400 (EC-ATT-01); mark >2h late → `late_mark` + audit (EC-ATT-02); geo outside → `flagged` + audit (EC-ATT-03); frozen-year block.
- **Reports:** shortage list respects threshold (F-105); exam-day excluded when setting off (EC-ATT-05); monthly/subject numbers correct (F-110); detention auto-list (F-115).
- **Leave:** student applies → pending; admin/faculty approve → student's date shows `leave`; reject with note (F-106/183/197).
- **Corrections:** PATCH record → original preserved in audit diff (EC-ATT-04, F-107).
- **Student/parent:** subject-wise % correct (F-111); parent can only see linked child (F-112 + StudentGuardianLink check); non-linked → 403.
- **Permissions:** student can't mark; faculty can't correct retroactively; cross-branch denied.
- Target: ~20 tests; keep full suite green.

---

## 9. Open Decisions (need your call before/while building)
1. **Does `late` count as present** in the %? (Common: yes. Default = yes, configurable later.)
2. **Marking granularity** — per **session (batch_subject+slot)** as planned, or simpler **per-day per-batch** (one mark/day)? PRD says session-level. Schools often want daily homeroom + subject-wise. *Recommend: session-level (matches PRD), with a daily summary derived.*
3. **Geo-fence**: store-and-flag only for now (radius config stub), full enforcement later? *Recommend yes.*
4. **Student link for AttendanceRecord** = `StudentProfile` (confirmed in §2) — OK to proceed?
5. **SMS absence alert** (F-112/216): wire the Celery/`sms.py` hook now (fire-and-forget) or defer to Stage 7? *Recommend: leave a no-op hook now.*

---

## 10. Build Order (sub-stages) & Effort
1. **Models + migration + factories** (½ day) — the 4 models, enums, admin.
2. **Marking vertical** (½ day) — session open, roster, bulk mark + EC-ATT-01/02/03/06, frozen guard. *Highest value; unblocks data.*
3. **% engine + reports** (½ day) — shortage, detention, monthly/subject, exam-day rule.
4. **Leave workflow** (½ day) — apply/queue/approve, leave→status integration.
5. **Corrections + audit + flagged queue** (½ day) — F-107/108/103.
6. **Student/parent read views** (¼ day) — summaries, parent link check.
7. **Live board + tests + polish** (½ day) — polling board, full test pass.

**Estimate: ~3 dev-days** (vs roadmap's 2 — the audit + leave + %-engine add depth). Powers Admin **Attendance** + feeds **Dashboard**, and pre-builds the faculty/student/parent attendance backends for Phases 2–4.

---

## 11. Risks
- **Enrollment seam (§2)** — the single biggest design coupling; documented and isolated to the `student` FK so Stage 5 is a contained migration.
- **% semantics** — schools disagree on late/excused handling; we make it config-driven via `TenantSettings`.
- **Volume/partitioning** — fine for Phase 1; flag partitioning for prod (PRD §indexing).
