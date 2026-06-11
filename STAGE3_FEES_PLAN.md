# Stage 3 — Fees & Payments: Detailed Implementation Plan

> **Status:** PLAN ONLY — no code yet. Reviewed against `features.md` (F-136–F-155, F-201/206/214/153), `edge_cases.md` (EC-FEE-01–09), `data_models.md` §8, `user_flows.md` Flow 5, and the frontend `packages/types/src/admin/fees.ts` contract.
>
> This is the **most complex stage**: real money, an external gateway (Razorpay), idempotency under webhooks, gap-free receipts, and integer-paise accounting.

---

## 0. CRITICAL — which "fees" this is

There are **two money flows** in EduOS; this stage is **only the first**:

| | **Flow A — this stage** | Flow B — already in PRD (Flow 21 / §1b) |
|---|---|---|
| Who pays whom | **Parent/student → School** | School → Platform owner |
| What | **Tuition / transport / exam fees** | SaaS per-student subscription |
| App | `apps.fees` | `apps.organizations` (SubscriptionPricing/StudentSeat) |

Stage 3 = **school fee collection** (tuition etc.), via Razorpay, with invoices/receipts/refunds. Do **not** conflate with the per-student SaaS billing.

---

## 1. Goal & Scope

Make the Admin **Fees** module work end-to-end and give students/parents a fee portal: define fee structures, assign them to students, generate invoices, collect online (Razorpay) and offline, issue gap-free receipts, reconcile, refund, and handle concessions/credit notes.

**In scope (Phase 1):**
- Models: FeeStructure, StudentFeeAssignment, FeeInvoice/FeeInvoiceLine, Installment, Payment, Receipt, Refund, ConcessionRule, ConcessionRequest, CreditNote, WebhookEventLog
- **Razorpay adapter** (in `apps.integrations`) with a **sandbox/mock mode** so the flow runs without live keys
- Payment flow (Flow 5): order → checkout → webhook/verify → idempotent ledger → sequential receipt
- Collection dashboard, defaulters, reconciliation, refunds, concessions, credit notes
- Student/parent fee portal (dues, pay, receipts, history)
- All edge cases EC-FEE-01..09

**Out of scope / deferred (hooks left):**
- **Exam-fee → hall-ticket gate (F-152)** — depends on Examinations (Stage 4). Leave the `ExamFeeInvoice`/gate hook but don't wire hall tickets.
- **Branch-transfer dues (F-155)** — depends on super-admin transfer (Stage 9 area). Leave dues in source branch; no transfer logic yet.
- **Real receipt PDF to S3** — generate a minimal PDF or store a stub key; full S3 + templating later.
- **True table partitioning** — note in docstrings (PRD), not needed at Phase-1 scale.

---

## 2. Critical dependencies & decisions

1. **StudentEnrollment seam (same as attendance).** PRD keys invoices/payments off `student_enrollment_id`, but Admissions (Stage 5) isn't built. **Decision:** key fees off **`accounts.StudentProfile`** (one FK, documented seam) — identical pattern to attendance. Swap to enrollment in Stage 5 via a contained migration.
2. **Razorpay adapter with sandbox mode.** `apps.integrations` already has an `adapters/` dir. Build a `PaymentGateway` interface (`create_order`, `fetch_payment`, `verify_webhook_signature`, `create_refund`) with two implementations: **live** (PyJWT/requests against Razorpay) and **sandbox** (deterministic fake order/payment ids, signature = HMAC of a known test secret). A setting `PAYMENTS_GATEWAY_MODE = sandbox | live` selects. **All Phase-1 tests run in sandbox.**
3. **Money is integer paise (`BigIntegerField`), never float (F-149).** Display uses **banker's rounding** (`decimal.ROUND_HALF_EVEN`) — a pure helper, unit-tested (EC-FEE-08).
4. **Receipts are gap-free per `(branch, financial_year)` (F-145/EC-FEE-09).** Allocate the sequence number inside the same DB transaction as the payment capture, using `select_for_update()` on a per-branch counter so concurrent captures can't gap or reuse (EC-FEE-09).
5. **Webhooks are the source of truth, and idempotent (EC-FEE-01/02).** Verify HMAC signature (reject 400 if bad), then dedupe on `razorpay_payment_id` via `WebhookEventLog` (second delivery → 200 no-op).

---

## 3. Models (`apps/fees/models/`)

Split per pattern: `enums.py`, `models/structure.py`, `models/assignment.py`, `models/invoice.py`, `models/payment.py`, `models/concession.py`, `models/__init__.py`. All inherit `core.BaseModel` (UUID, timestamps, soft-delete, `version`, audit).

### 3.1 Enums
```
InvoiceStatus     = due | partial | paid | written_off
PaymentStatus     = created | pending | captured | failed | refunded | requires_review
PaymentMethod     = razorpay | cash | cheque | bank_transfer
RefundStatus      = requested | approved | processed | failed
ConcessionStatus  = pending | approved | rejected
CreditNoteStatus  = pending | approved | rejected
FeeComponentKind  = tuition | transport | hostel | exam | other
```

### 3.2 FeeStructure (`structure.py`) — F-136/F-150
| Field | Type | Notes |
|---|---|---|
| branch | FK | |
| batch | FK academics.Batch (nullable) | structure may be course- or batch-level |
| academic_year | FK academics.AcademicYear | |
| name | varchar | "Grade 9 — 2024-25" |
| components | JSON | `[{kind, label, amount_paise, due_date, installment_no}]` |
| version | int | **F-150: bump on edit; enrolled students keep their snapshot** |
**Index:** `(branch, academic_year)`

### 3.3 StudentFeeAssignment (`assignment.py`) — F-150/EC-FEE-06
| Field | Type | Notes |
|---|---|---|
| student | FK StudentProfile | (enrollment seam) |
| fee_structure | FK FeeStructure | |
| structure_snapshot | JSON | **frozen copy of components at assignment time** |
| discount_lines | JSON | applied concessions `[{label, amount_paise}]` |
| **Unique** | `(student, fee_structure)` | |

> EC-FEE-06: editing a FeeStructure does NOT change existing assignments — they read `structure_snapshot`.

### 3.4 FeeInvoice + FeeInvoiceLine + Installment (`invoice.py`) — F-140/F-148
| FeeInvoice | Type | Notes |
|---|---|---|
| branch, student | FK | |
| assignment | FK StudentFeeAssignment | |
| billing_guardian | FK GuardianProfile (nullable) | who to bill (via StudentGuardianLink) |
| due_date | date | |
| total_paise | bigint | **≥ 0; ₹0 allowed (F-148)** |
| paid_paise | bigint | running total |
| status | InvoiceStatus | due/partial/paid/written_off |
| version | int | |
| FeeInvoiceLine | line per component (`kind, label, amount_paise`) |
| Installment | `invoice, sequence, amount_paise, due_date, paid_paise, status` (F-140) |
**Index:** `(branch, status, due_date)`

### 3.5 Payment + Receipt + Refund (`payment.py`)
| Payment | Type | Notes |
|---|---|---|
| invoice | FK | |
| amount_paise | bigint | |
| method | PaymentMethod | |
| status | PaymentStatus | |
| razorpay_order_id | varchar UNIQUE NULL | |
| razorpay_payment_id | varchar UNIQUE NULL | |
| payer | FK User (nullable) | student/parent/admin |
| captured_at | datetime? | |
| idempotency_key | varchar UNIQUE | EC-FEE-04 |

| Receipt | Type | Notes |
|---|---|---|
| branch, payment (UNIQUE) | FK | |
| sequence_number | int | **gap-free per (branch, financial_year)** |
| financial_year | varchar | e.g. "2024-25" |
| pdf_s3_key | varchar | stub key in Phase 1 |
| issued_at | datetime | |
| **Unique** | `(branch, financial_year, sequence_number)` |

| Refund | Type | Notes |
|---|---|---|
| payment | FK | |
| amount_paise | bigint | |
| reason, status | RefundStatus | |
| approved_by | FK User? | |
| razorpay_refund_id | varchar UNIQUE NULL | |
| idempotency_key | varchar UNIQUE | |

| ReceiptCounter | `branch, financial_year, last_number` — UNIQUE `(branch, financial_year)`; the row we `select_for_update()` to allocate gap-free numbers |

### 3.6 Concession + CreditNote + WebhookEventLog (`concession.py`)
| ConcessionRule (F-137) | `branch, name, kind, amount_paise or percent, criteria JSON` |
| ConcessionRequest | `student, rule?, amount_paise, status (pending/approved/rejected), requested_by, approver?, decided_at, note` — **approval workflow** |
| CreditNote (F-151/EC-FEE-07) | `student, invoice?, amount_paise, reason, status (pending/approved/rejected), approved_by` — retroactive scholarship |
| WebhookEventLog | `event_id UNIQUE, razorpay_payment_id, payload JSON, processed_at` — idempotent webhooks (EC-FEE-02) |

---

## 4. Razorpay integration (`apps/integrations/adapters/`)

```python
class PaymentGateway(Protocol):
    def create_order(amount_paise, currency, receipt, notes) -> {order_id, ...}
    def fetch_payment(payment_id) -> {status, amount, order_id, ...}
    def verify_webhook_signature(body: bytes, signature: str) -> bool
    def create_refund(payment_id, amount_paise) -> {refund_id, status}
```
- **SandboxGateway** — deterministic: `order_id = f"order_sandbox_{uuid}"`, signature = HMAC-SHA256(body, settings.RAZORPAY_WEBHOOK_SECRET); `fetch_payment` returns `captured`. Lets every test run without network.
- **RazorpayGateway** — real HTTP. Selected when `PAYMENTS_GATEWAY_MODE=live`.
- A factory `get_gateway()` reads the setting. **All DB writes still go through `apps.fees.queries`** — the gateway only talks to Razorpay.

---

## 5. Endpoint surface (`/api/v1/fees/`)

camelCase to match `admin/fees.ts`. Perms: A=admin, SA=super-admin, S=student, P=parent.

### Admin — structures & assignments
| Method | Path | Purpose | F |
|---|---|---|---|
| GET/POST | `/structures/` | list/create fee structures | F-136 |
| PATCH | `/structures/<id>/` | edit (bumps version) | F-136/150 |
| POST | `/assignments/` | assign structure → student (snapshots) | F-150 |
| POST | `/invoices/generate/` | generate invoices for a batch/period | F-136/140 |

### Admin — concessions, refunds, credit notes
| GET/POST | `/concession-rules/` | define rules | F-137 |
| GET | `/concession-requests/?status=` | queue | F-137 |
| PATCH | `/concession-requests/<id>/` | approve/reject | F-137 |
| GET | `/refunds/?status=` · PATCH `/refunds/<id>/` | refund approval | F-146 |
| POST | `/credit-notes/` · PATCH `/credit-notes/<id>/` | retroactive scholarship | F-151/EC-FEE-07 |

### Admin — dashboards & ops
| GET | `/collection/` | real-time collection metrics | F-138 |
| GET | `/defaulters/` | defaulter list + escalation | F-139 |
| GET | `/reconciliation/` | pending payments needing reconcile | F-143 |
| GET | `/ledger/export/` | background export job | F-147 |

### Payments (student/parent/admin) — Flow 5
| POST | `/orders/` | create Razorpay order (idempotency-key) | F-141 |
| POST | `/payments/verify/` | client-side verify after checkout | F-141 |
| POST | `/webhook/` | Razorpay webhook (HMAC, idempotent) | F-142/EC-FEE-01/02 |
| POST | `/payments/offline/` | admin records cash/cheque | F-136 |

### Student / parent portal
| GET | `/me/dues/` | student's invoices + balances | F-154 |
| GET | `/me/receipts/` | receipts + history | F-154 |
| POST | `/me/pay/` | start payment for an invoice (→ order) | F-206 |
| GET | `/children/<studentId>/dues/` · `/children/<studentId>/pay/` | parent pays child (link-checked) | F-153/214 |

---

## 6. Edge cases — where each is enforced

| EC | Where | Detail |
|---|---|---|
| **EC-FEE-01** bad webhook signature | webhook view | `verify_webhook_signature` fails → **400**, no ledger change |
| **EC-FEE-02** duplicate webhook | webhook interactor | dedupe on `WebhookEventLog.event_id` / `razorpay_payment_id` → 200 no-op |
| **EC-FEE-03** payment pending 5+ min | Celery `reconcile_payment` task | poll `fetch_payment`; capture or mark `requires_review` |
| **EC-FEE-04** duplicate client payment, same order | order/verify interactor | second capture on a paid invoice → route to **refund workflow** |
| **EC-FEE-05** partial installment | payment interactor | invoice/installment → `partial`; balance = total − paid |
| **EC-FEE-06** structure changed post-enroll | assignment read | reads `structure_snapshot`, not the live structure |
| **EC-FEE-07** retroactive scholarship | credit-note interactor | creates `CreditNote` (pending) → admin approval → ledger credit |
| **EC-FEE-08** rounding display | `paise.py` helper | banker's rounding (ROUND_HALF_EVEN); unit test |
| **EC-FEE-09** receipt sequence gap | receipt allocator | `select_for_update()` on `ReceiptCounter` inside the capture txn — rollback can't gap |

### Capture flow (the heart — Flow 5)
```
order: POST /orders/  → create Payment(status=created) + gateway.create_order → return order_id
        (idempotency_key prevents duplicate orders for the same invoice)
capture (whichever arrives first — webhook or verify):
   @transaction.atomic
     verify signature (webhook) / fetch_payment (verify)
     if already captured (WebhookEventLog/payment_id) → no-op (EC-FEE-02)
     Payment.status = captured
     invoice.paid_paise += amount; recompute status due→partial→paid (EC-FEE-05)
     allocate gap-free Receipt number (select_for_update on counter)  (F-145/EC-FEE-09)
     create Receipt (+ stub PDF key)
   → return receipt
duplicate capture on a paid invoice → Refund(requested)  (EC-FEE-04)
```

---

## 7. Architecture
```
views/       thin: validate → interactor → camelCase response
interactors/ business logic + @transaction.atomic (capture, refund, receipt allocation, concession/credit approval)
queries/     ALL ORM (structures, assignments, invoices, payments, receipts, refunds, counters, webhooks)
serializers/ camelCase matching admin/fees.ts
helpers/     paise math + banker's rounding + financial-year calc
integrations/adapters/  Razorpay gateway (sandbox/live) — the ONLY code that calls Razorpay
permissions  reuse accounts (IsAdminOrSuperAdmin, IsStudent, IsParent)
```
**Rules:** integer paise everywhere; all ORM in `queries/`; the gateway never touches the DB; receipt-number allocation always inside the capture transaction.

---

## 8. File-by-file build plan
```
apps/fees/
  enums.py · helpers/paise.py
  models/{structure,assignment,invoice,payment,concession}.py + __init__.py  → migrate
  queries/{structure,assignment,invoice,payment,receipt,refund,concession,webhook,report}.py
  interactors/{structure,assignment,invoice,payment,refund,concession,creditnote,report}.py
  serializers/{structure,invoice,payment,concession}.py  (camelCase)
  views/{structure,invoice,payment,webhook,report,portal}.py
  tasks.py   (reconcile_payment, ledger_export)
  urls.py    (already mounted at /api/v1/fees/)
  tests/{test_structure,test_payment_flow,test_webhook,test_receipts,test_refund,test_concession,test_portal,test_paise}.py
  tests/factories.py
apps/integrations/adapters/{base,razorpay,sandbox,factory}.py
```

---

## 9. Testing plan (each F/EC gets a test)
- **paise:** banker's rounding cases (EC-FEE-08); ₹0 invoice allowed (F-148).
- **structure/assignment:** edit structure → version bumps; assignment keeps snapshot (EC-FEE-06).
- **payment flow (sandbox):** order → webhook captures → invoice paid + receipt issued; partial pay → `partial` + balance (EC-FEE-05).
- **webhook:** bad signature → 400 no change (EC-FEE-01); duplicate delivery → 200 no-op, one receipt (EC-FEE-02).
- **duplicate payment:** second capture on paid invoice → refund workflow (EC-FEE-04).
- **receipts:** concurrent captures → sequential, gap-free; forced rollback mid-sequence leaves no gap (EC-FEE-09).
- **reconciliation:** pending order → task captures/flags (EC-FEE-03).
- **refund:** request → approve → gateway refund → ledger adjust (F-146).
- **concession/credit note:** request → approve → discount/credit applied (F-137/F-151/EC-FEE-07).
- **portal:** student dues/receipts; parent pays only linked child (F-153/154/206/214); non-linked → 403.
- **permissions:** student can't define structures; cross-branch denied.
- Target: ~28 tests; full suite stays green.

---

## 10. Build order (sub-stages) & effort
1. **paise helper + models + migration + factories** (½ d)
2. **Razorpay adapter (sandbox + live skeleton)** (½ d) — unblocks the flow
3. **Structures + assignments + invoice generation** (½ d)
4. **Payment capture flow + sequential receipts** (1 d) — *the core; EC-FEE-01/02/04/05/09*
5. **Reconciliation (Celery) + refunds** (½ d) — EC-FEE-03, F-146
6. **Concessions + credit notes** (½ d) — F-137/151, EC-FEE-07
7. **Collection dashboard + defaulters + ledger export** (½ d) — F-138/139/147
8. **Student/parent portal + tests + polish** (½ d)

**Estimate: ~4 dev-days** (matches roadmap's 3–4). Powers Admin **Fees** + feeds **Dashboard**, and pre-builds the student/parent fee backends for Phases 3–4.

---

## 11. Open decisions (confirm before/while building)
1. **Student link** = `StudentProfile` (enrollment seam) — OK to proceed? *(recommend yes, matches attendance.)*
2. **Razorpay** = sandbox mode now, live adapter skeleton wired but inactive until keys provided? *(recommend yes.)*
3. **Receipt PDF** — generate a minimal real PDF now, or store a stub `pdf_s3_key` and defer rendering? *(recommend stub key now; real PDF later with the pdf skill.)*
4. **Exam-fee gate (F-152)** — leave the model + a `gate` hook but don't block hall tickets (Examinations is Stage 4)? *(recommend yes.)*
5. **Offline payments** (cash/cheque) — include now (admin records, still issues a sequential receipt)? *(recommend yes — many Indian schools collect cash.)*

---

## 12. Risks
- **Idempotency under concurrent webhook + client-verify** is the trickiest correctness area — both paths converge on one atomic capture guarded by `WebhookEventLog`/payment_id. Heavily tested.
- **Receipt gap-freeness** under concurrency — solved with `select_for_update()` on a per-branch counter; tested with a forced mid-sequence rollback.
- **Money correctness** — integer paise end-to-end; floats never touch amounts; rounding only at display.
- **Enrollment seam** — same contained risk as attendance; isolated to the `student` FK.
- **Razorpay live wiring** — sandbox covers Phase 1; live needs real keys + webhook URL config (a deployment task, not Phase-1 code).
