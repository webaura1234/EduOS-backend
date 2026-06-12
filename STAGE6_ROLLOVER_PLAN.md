# Stage 6 — Academic-Year Rollover (enrollment-aware): Detailed Implementation Plan

> Same discipline as Stages 1–5: per-entity models, **all ORM in `queries/`**, thin views →
> interactors (`@transaction.atomic`) → queries, camelCase serializers, optimistic
> `version`. This stage **evolves an existing module** rather than building greenfield.

---

## 0. Current state — this is an EVOLUTION, not a new build

`apps/academics/` already ships a working rollover from **Stage 1**:
`models/rollover.py` (`AcademicRolloverRun` with `snapshot` JSON, `undo_expires_at`,
`preview_version`, status), `queries/rollover.py` (156 LOC), `interactors/rollover.py`
(preview / execute / undo / status), `serializers/rollover.py`, `views/rollover.py`,
`urls.py`, migration `0003_academicrolloverrun`, and `tests/test_rollover.py` (4 tests:
preview, execute-promotes-and-freezes, stale-version reject, undo-restores).

**The gap:** that rollover was written *before* `StudentEnrollment` existed, so it promotes
students by mutating **`StudentProfile.current_batch`** and snapshots `profile → batch` for
undo. It has **no concept of**: per-year `StudentEnrollment` rows, `backlog_subjects`,
arrears (EC-ROL-05), or `JobRun`-style saga tracking. Stage 6 closes that gap.

> **Net effect of Stage 5 (Option A):** every attendance/fee/exam row already keys off
> `StudentEnrollment`. Rollover producing a **new enrollment per student per year** is now
> the clean, correct way to advance a cohort — new-year rows attach to the new enrollment;
> last-year rows stay attached to the old one. This stage makes rollover create those rows.

---

## 1. Goal & scope

Turn the year-and-batch rollover into an **enrollment-aware promotion** (F-070 / F-036 /
F-058) that:

1. **Previews** the promotion plan per branch (who advances to which batch, who graduates,
   who carries arrears) — read-only, manual only (EC-ROL-01, F-070).
2. **Executes** atomically: freezes the old year, creates/sets the new current year, and for
   each active student creates a **new `StudentEnrollment`** for the promoted batch in the
   new year; mirrors `StudentProfile.current_batch`.
3. **Graduates** final-year students (no next course) → `academic_status=graduated`,
   `current_batch=None`, no new enrollment (EC-ROL-03).
4. **Carries arrears (college, EC-ROL-05):** copies `backlog_subjects[]` to the new
   enrollment; leaves arrear `ExamRegistration` rows intact (not archived); a final-year
   student with a non-empty `backlog_subjects[]` is **not** graduated until it empties; the
   exam hub surfaces those as `status=pending_arrear`.
5. **Undo within 24h** (EC-ROL-02): soft-rollback restores prior `current_batch`, soft-
   deletes the new enrollments, un-freezes the old year. After 24h → 403 (EC-ROL-04).
6. **Tracks the run** as a saga-shaped record (the existing `AcademicRolloverRun` + a
   richer snapshot) so admin can see per-step status (F-269 seam).

**Out of scope (later):** real Celery + Redis Redlock singleton execution (F-267) and the
generic `JobRun` table (F-269) — we keep synchronous execution inside one
`@transaction.atomic` and use `AcademicRolloverRun.snapshot` as the saga/compensation
record, leaving a documented seam. Step-up auth on undo (F-262) is an Auth-stage seam.
Seat-billing re-activation for the new year (Flow 21 / F-334) is the billing stage's job;
rollover only advances academic records.

---

## 2. Critical dependencies & decisions

| # | Decision | Resolution |
|---|----------|-----------|
| D1 | Promotion now creates enrollments | For each promoted student, `admissions.queries.enrollment.create_enrollment(branch, student_profile, batch=next_batch, academic_year=new_year, backlog_subjects=carried)`. academics calls the **admissions query layer**, never `StudentEnrollment.objects` directly. |
| D2 | Old enrollment lifecycle | The prior-year enrollment **stays** (`is_active=True`, historical) — it's the anchor for that year's attendance/fees/exams. The `(student_profile, academic_year)` unique constraint guarantees one per year, so the new-year row is distinct. "Current" = newest by year. |
| D3 | `current_batch` mirror | Keep mutating `StudentProfile.current_batch` to the promoted batch (the existing resolver and many reads still use it). Enrollment + mirror stay in sync, exactly as the Stage-5 provisioning saga does. |
| D4 | Next-batch resolution | Reuse the existing `_get_next_course` / next-batch logic. The promoted student needs a **target batch in the new year**; if none exists for the next course, the plan flags it (admin must create batches first) rather than silently failing. |
| D5 | Arrears source (EC-ROL-05) | A student's open arrears = subjects with a failing/!pass `StudentResult` or `ExamRegistration.is_arrear=True` not yet cleared. Read via `examinations.queries` (a new `open_arrear_subjects(enrollment_id)` helper). Copied into `new_enrollment.backlog_subjects` as `[{subjectId, examId}]`. Arrear `ExamRegistration` rows are **left intact**. |
| D6 | Graduation guard (EC-ROL-05) | Final-year (no next course) **and** empty `backlog_subjects` → graduated. Final-year **with** open backlog → stays active, gets a new enrollment in the same final batch carrying the backlog (so they can re-sit), not graduated. |
| D7 | Undo snapshot | Extend `snapshot` to record, per student: `prior_current_batch_id`, `prior_academic_status`, and the **created `enrollment_id`**. Undo restores the first two and soft-deletes the created enrollment; un-freezes the old year and clears `to_year` current flag. 24h window already enforced via `undo_expires_at` (EC-ROL-02/04). |
| D8 | Manual only (EC-ROL-01) | No Celery beat / cron entry. Execution is admin-triggered through the endpoint only; test asserts no periodic task is registered. |
| D9 | Concurrency | `preview_version` optimistic check already rejects stale execute (existing test). Add a guard that a branch cannot have two **in-flight** (undoable) runs at once → 409. Redis Redlock (F-267) is the future hardening. |

---

## 3. Models (`apps/academics/models/rollover.py`)

`AcademicRolloverRun` already exists and is sufficient. **One additive change:** enrich the
`snapshot` JSON shape (no schema migration needed — it's a `JSONField`):

```jsonc
snapshot = {
  "from_year_id": "...",
  "to_year_id": "...",
  "students": [
    {
      "student_profile_id": "...",
      "prior_current_batch_id": "...",
      "prior_academic_status": "active",
      "action": "promoted | graduated | retained_arrear",
      "new_enrollment_id": "...",          // null for graduated
      "new_batch_id": "...",
      "backlog_subjects": [{"subjectId": "...", "examId": "..."}]
    }
  ]
}
```

No new model. (If/when F-269's generic `JobRun` lands, this run becomes one JobRun row; the
snapshot becomes its compensation payload.)

---

## 4. Rollover flow (the heart) — `interactors/rollover.py`

**`build_preview(branch, tenant)` (F-070, EC-ROL-03):** for each active student in the
current year, compute `action` (promoted → next batch / graduated → final / retained_arrear),
the target batch, and (college) the carried `backlog_subjects`. Flag students whose next
batch doesn't exist yet. Read-only; returns a `RolloverPreviewDTO`.

**`execute_rollover(branch, tenant, expected_version, user)` — one `@transaction.atomic`:**
1. Optimistic `preview_version` check (existing) → 409 on mismatch; reject if an undoable run
   already exists (D9).
2. Freeze `from_year`; create/flag `to_year` as current (existing logic).
3. For each active student, via the **admissions + examinations query layers**:
   - compute arrears (D5); decide promote / graduate / retain (D6);
   - `create_enrollment(...)` for promote/retain with carried `backlog_subjects`;
   - `graduate_student(...)` for final-year-no-backlog;
   - mirror `current_batch`;
   - append the per-student snapshot entry (D7).
4. Persist `AcademicRolloverRun` (status `SUCCEEDED`, `undo_expires_at = now + 24h`).
5. Return summary `{promoted, graduated, retainedArrear, undoExpiresAt}`.

**`undo_rollover(branch, user)` (EC-ROL-02/04):** verify `undo_window_active` (else 403);
walk the snapshot in reverse — soft-delete each `new_enrollment_id`, restore
`prior_current_batch_id` + `prior_academic_status`, un-freeze `from_year`, drop `to_year`
current. Mark run `COMPENSATED`.

**`get_rollover_status(branch)`:** latest run + `canUndo`.

---

## 5. Endpoint surface (`/api/v1/academics/rollover/`) — already wired, extended

`GET preview/` (promotion plan) · `POST execute/` (body: `expectedVersion`) ·
`POST undo/` · `GET status/`. No new routes; payloads grow to include
`graduated[]`, `retainedArrear[]`, and per-student `backlogSubjects`.

---

## 6. Edge cases — where each is enforced

| Code | Rule | Enforced in |
|------|------|-------------|
| EC-ROL-01 | No auto cron — manual only | no beat task; test asserts none registered |
| EC-ROL-02 | Undo within 24h restores | `undo_rollover` + snapshot replay |
| EC-ROL-03 | Final-year → graduated, read-only | `build_preview` / `execute` graduation branch |
| EC-ROL-04 | Undo after 24h → 403 | `undo_window_active` guard |
| EC-ROL-05 | College arrears carried; arrear regs intact; not graduated until cleared; hub shows pending_arrear | `execute` arrear branch (D5/D6) + exam-hub `pending_arrear` surfacing |
| F-070 | Preview screen + 24h undo | preview endpoint + `undo_expires_at` |
| F-269 (seam) | Saga/step status visible | `AcademicRolloverRun.snapshot` + status |

---

## 7. Architecture (non-negotiable)

Thin views → interactors (`@transaction.atomic`) → queries. **`.objects`/`.save()` only in
`queries/`.** Rollover (academics) reaches **admissions** (`create_enrollment`,
`update_enrollment`, soft-delete), **examinations** (`open_arrear_subjects`), and
**accounts** (`graduate_student`, `current_batch` mirror) **only through their query
layers**. Verify after every change:
`grep -rn "\.objects\.\|\.save(" apps/academics/interactors/rollover.py apps/academics/views/rollover.py` → empty.

---

## 8. File-by-file build plan

```
models/rollover.py        (no change — snapshot shape documented)
queries/rollover.py       enrich snapshot capture/restore; add undoable-run guard;
                          stop mutating only current_batch — call admissions enrollment q
admissions/queries/enrollment.py   (reuse create_enrollment / update_enrollment /
                                    soft-delete; add `soft_delete_enrollment` if missing)
examinations/queries/*    add `open_arrear_subjects(enrollment_id)` + hub `pending_arrear`
interactors/rollover.py   promote→create_enrollment, graduate guard w/ backlog,
                          arrear carry, undo soft-deletes enrollments
serializers/rollover.py   add graduated[]/retainedArrear[]/backlogSubjects to preview+result
views/rollover.py         (thin — unchanged surface)
tests/test_rollover.py    extend with enrollment + arrears + graduation cases
```

Then `makemigrations` (expected: none — snapshot is JSON, no field changes), `migrate`,
`check`, `makemigrations --check`.

---

## 9. Testing plan (extend the existing 4 tests)

Keep the current 4 green, then add:
- **Promotion creates enrollment:** after execute, the promoted student has a **new
  `StudentEnrollment`** in the new year + promoted batch; `current_batch` mirrors it.
- **EC-ROL-03 graduation:** final-year student → `graduated`, no new enrollment.
- **EC-ROL-05 arrears:** seed a college student with 2 open arrear subjects → execute →
  new enrollment `backlog_subjects` matches; original arrear `ExamRegistration` rows intact;
  final-year-with-arrears is **not** graduated; exam hub shows 2 `pending_arrear` entries.
- **EC-ROL-02 undo:** undo soft-deletes the new enrollment and restores prior batch/status.
- **EC-ROL-04:** undo after the window → 403.
- **EC-ROL-01:** assert no periodic/cron task triggers rollover.
- Full suite must stay green (currently **211**) with **zero** ORM-outside-queries.

Command (unchanged):
```
export PATH="$HOME/.local/bin:$PATH" && unset USE_POSTGRES DATABASE_URL && \
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest -p no:cacheprovider -q
```

---

## 10. Build order (sub-stages) & effort

| Sub-stage | Content | Effort |
|-----------|---------|--------|
| 6.0 | `open_arrear_subjects` query + exam-hub `pending_arrear` surfacing | M |
| 6.1 | Rewire `execute` to create enrollments (promote/retain) + mirror | **L** |
| 6.2 | Graduation guard with backlog (EC-ROL-03/05/D6) | M |
| 6.3 | Enriched snapshot + undo that soft-deletes enrollments (EC-ROL-02/04) | M |
| 6.4 | Preview payload + serializers (graduated/retainedArrear/backlog) | S |
| 6.5 | Undoable-run + stale-version guards (D9) | S |
| 6.6 | Tests (all EC-ROL) + full-suite green + queries scan | M |

6.1 carries the real work — turning a `current_batch` mutation into an enrollment-creating
promotion while keeping undo correct.

---

## 11. Decisions (resolved — all confirmed by the product owner)

- **OD-1 — arrear source of truth: DERIVE FROM FAILED RESULTS.** Open arrears come from
  `StudentResult.is_pass = False` (fall back to `ExamRegistration.is_arrear`). Automatic;
  no manual flag to maintain.
- **OD-2 — retained-arrear batch: SAME FINAL BATCH.** A final-year student with backlog gets
  a new enrollment in their existing final batch to re-sit; no dedicated arrear pseudo-batch.
- **OD-3 — fee snapshot on promotion: NO.** Rollover advances academic records only; the
  new year's `StudentFeeAssignment` is created later by the admin / seat-billing step so
  structures and prices can change first.
- **OD-4 — job tracking: REUSE `AcademicRolloverRun`.** Its `snapshot` JSON is the saga /
  compensation record; the generic `JobRun` table (F-269) is deferred to the Operations
  stage.

---

## 12. Risks

- **Undo correctness** is the top risk: undo must soft-delete exactly the enrollments the run
  created and restore prior batch/status without touching unrelated rows — the snapshot must
  be the single source of truth, replayed in reverse. EC-ROL-02 is the guard.
- **Resolver ambiguity post-rollover:** a student now has ≥2 enrollments across years;
  `resolve_enrollment_for_profile` returns the newest, and year-scoped reads pass
  `academic_year` — verify no current-year write accidentally lands on a prior enrollment.
- **Arrears semantics (EC-ROL-05)** are subtle: keep arrear `ExamRegistration` rows intact,
  don't graduate until backlog clears, surface `pending_arrear` — the test must assert all
  three, not just the batch change.
- **Cross-app boundary:** academics→admissions/examinations/accounts strictly through query
  layers; a stray `.objects` breaks the rule and the scan.
```
