# Stage 8 — Communications + Integrations: Detailed Implementation Plan

> Same discipline as Stages 1–7: per-entity models, **all ORM in `queries/`**, thin views →
> interactors (`@transaction.atomic`) → queries, camelCase serializers, optimistic `version`.
> **Everything external is behind a sandbox adapter** (the Razorpay `SandboxGateway` pattern
> already in `apps/integrations/adapters/payments.py`): tests assert against *recorded intent*,
> never a live network call. This is what makes the whole stage testable now.

---

## 0. Current state — two greenfield apps

`apps/communications/` and `apps/integrations/` are **registered but empty skeletons**
(in `INSTALLED_APPS`, urls wired at `api/v1/communications/` and `api/v1/integrations/`).
Trees exist (communications: `notification`/`announcement`; integrations:
`webhook`/`infra`, `adapters/`, `circuit_breaker`/`outbox`/`webhook` interactors), but every
file is a stub — **except** `integrations/adapters/payments.py`, the Razorpay sandbox gateway
built in Stage 3. That adapter is the template for every adapter here.

Also already present from earlier stages: `fees.WebhookEventLog` (inbound Razorpay webhook
dedupe, EC-FEE-02) and the `idempotency_key` columns on `Payment`/`Receipt`.

---

## 1. Goal & scope

**Communications (F-171 – F-180, F-289):**
1. **Notifications** — a dispatch pipeline that decides recipients, applies preferences and
   all skip rules, sends via channel adapters, and writes an immutable `NotificationLog`.
2. **Announcements** (F-171) — branch/role/batch-targeted broadcasts over in-app + SMS + email.
3. **Channels** — SMS (MSG91 DLT), email, push (FCM/APNs), in-app — all via sandbox adapters.
4. **Preferences** (F-179) + per-user **flood cap** (F-180) + tenant **rate limit** (F-175).
5. **Automated triggers** (F-178) — absence / fee-due / result-published emit notifications.

**Integrations / reliability (F-264 – F-269, F-015):**
6. **Idempotency infrastructure** (F-266) — `IdempotencyKey` table; replay returns the cached
   response; 409 on key reuse with a different body.
7. **Transactional outbox** (F-264) — every cross-system side effect is an `OutboxEvent` row
   written in the same DB transaction; a relay dispatches it.
8. **Outbound webhooks** (F-265) — tenant `WebhookSubscription`s; HMAC-signed payloads; retry
   schedule 1m/5m/30m/2h/12h; after 5 attempts → DLQ; admin replay.
9. **Circuit breaker** (F-268) — adapters open after 5 failures/30s, half-open probe after 60s;
   open → typed `IntegrationUnavailable`.
10. **JobRun tracker** (F-269) + **integration health** (F-015) dashboard read.

**Out of scope (later stages):** real MSG91/FCM/SMTP credentials (we ship sandbox adapters;
the live swap is one line), real Celery beat + Redis relay/orphan-sweeper (we run the relay
loop **synchronously / on demand** so it's testable, leaving the async seam), **WebSocket /
Channels real-time push** (EC-WS-* — needs Redis Channels; Phase-1 in-app notifications are
pull/poll), webhook-secret + PII encryption (F-281 — accessor seam now), and DSAR /
data-deletion / maintenance-window tables (Operations stage).

---

## 2. Critical dependencies & decisions

| # | Decision | Resolution |
|---|----------|-----------|
| D1 | **Adapters are sandbox-first** | Each external channel (`MSG91`, `Email`, `Push`, `Webhook HTTP`) has a `Sandbox*` adapter that records `(recipient, channel, payload, signature)` deterministically and a `Live*` adapter (stub) for prod. A `get_*_adapter()` factory reads `settings.COMMS_MODE` / `WEBHOOK_MODE` (default `sandbox`). Mirrors `payments.get_gateway()`. |
| D2 | **Dispatch is synchronous + on-demand** | The notification dispatch and the outbox/webhook relay run in-process (a function the test calls), inside `@transaction.atomic` where a side effect must be transactional. Celery beat is a documented seam. **OD-1.** |
| D3 | **Identity & dedup** | Dedup + flood are scoped to the person: `dedup_key = sha256(canonical(linked_user_group_id ?? user_id, notification_id, channel))`. Deactivation/skip is scoped to `user_id`. Matches data_models §10. |
| D4 | **Preference intersection** (F-289) | A notification is delivered on a channel only if BOTH the user-level `NotificationPreference(enabled)` AND (for guardian links) `StudentGuardianLink.receives_notifications` allow it. Either off → skip with `opt_out`. |
| D5 | **Event emission** | A single `emit_event(tenant, aggregate, event_type, payload)` helper writes an `OutboxEvent` (F-264). Notification triggers and webhook deliveries both fan out from outbox events. Phase 1 wires the **high-value emitters** (absence, fee-due, result-published, payment.captured, enrollment.created) and leaves a documented list for the rest. **OD-2.** |
| D6 | **Idempotency** | `IdempotencyKeyMiddleware`/mixin: for flagged POSTs, look up `(tenant, key, endpoint)`; hit with same body-hash → return cached response (EC-CONCUR-08); same key + different body → 409; missing key on a required endpoint → 400 `idempotency_key_required` (EC-API-01). |
| D7 | **Webhook security** | Outbound payload signed HMAC-SHA256 with the subscription secret (accessor seam, D-PII). Inbound replay guard reuses the fees pattern (timestamp > 5 min → `replay_detected`, EC-INT-03). |
| D8 | **Money / tenant guards** | Relay + dispatch check `Institution.status` at the write phase (EC-CEL-07): a deactivated tenant aborts with no side effect. |

---

## 3. Models

### Communications (`apps/communications/models/`)
- **`Announcement`** (F-171) — `branch` (null = tenant-wide), `title`, `body`,
  `target_filter` JSONB (`{roles, batchIds, departmentIds, all}`), `channels` JSONB,
  `scheduled_for`, `published_at`, `created_by`.
- **`NotificationLog`** — `tenant`, `announcement` (null), `trigger_event`, `channel`
  (`sms|email|in_app|push`), `recipient_user`, `status`
  (`queued|sent|delivered|failed|skipped`), `provider_id`, `dedup_key`, `skip_reason`
  (`dedup|self_marked|inactive|role_mismatch|quota|rate_limit|opt_out`), `attempt_count`,
  `last_error`. Index `(recipient_user, created_at)`, `(tenant, status)`.
- **`NotificationPreference`** (F-179) — `user`, `channel`, `category`, `enabled`.
  UNIQUE `(user, channel, category)`.

### Integrations (`apps/integrations/models/`)
- **`OutboxEvent`** (F-264) — `tenant`, `aggregate_type`, `aggregate_id`, `event_type`,
  `payload` JSONB, `dispatched_at`, `attempts`, `status` (`pending|dispatched|failed|dlq`).
  Index `(status, created_at)`.
- **`IdempotencyKey`** (F-266) — `tenant`, `user`, `key`, `endpoint`, `request_hash`,
  `response_status`, `response_body` JSONB, `expires_at`. UNIQUE `(tenant, key, endpoint)`.
- **`WebhookSubscription`** (F-265) — `tenant`, `url`, `secret` (accessor seam),
  `event_types` JSONB, `is_active`, `last_success_at`, `last_failure_at`, `created_by`.
- **`WebhookDelivery`** (F-265) — `subscription`, `event` (→ OutboxEvent), `url`, `status`
  (`pending|delivered|failed|dlq`), `attempts`, `next_attempt_at`, `response_status`,
  `last_error`. UNIQUE `(subscription, event)`.
- **`CircuitBreakerState`** (F-268) — `name` (adapter key), `state`
  (`closed|open|half_open`), `failure_count`, `opened_at`, `last_failure_at`. UNIQUE `(name)`.
- **`JobRun`** (F-269) — `tenant`, `job_type`, `status`
  (`pending|running|succeeded|failed|compensating|timed_out`), `started_at`, `ended_at`,
  `heartbeat_at`, `steps` JSONB, `input`/`result`/`error` JSONB. Index `(status, heartbeat_at)`.

---

## 4. The two pipelines (the heart)

### 4a. Notification dispatch — `interactors/notification.py`
`dispatch_notification(*, tenant, trigger_event, recipients, channels, payload, context)`:
for each `(recipient, channel)`, in order, decide and **log every outcome**:
1. **inactive** → `recipient.is_active is False` → skip `inactive` (EC-NOT-01/F-176).
2. **role mismatch** → recipient role ∉ intended audience → skip `role_mismatch` (EC-NOT-03/F-177; announcement create also 400-validates audience upfront).
3. **self_marked** (EC-NOT-05) → absence SMS where the marking faculty and the recipient
   parent share a `linked_user_group_id` → skip `self_marked`; **no adapter call**.
4. **opt_out** (D4) → user pref OR guardian-link pref disabled → skip `opt_out` (F-179/F-289).
5. **dedup** (EC-NOT-06) → `dedup_key` already logged delivered for this notification+channel
   (same person via linked group) → skip `dedup`.
6. **rate_limit / quota** → tenant > 100/min (F-175/EC-NOT-02) → status `queued` +
   `rate_limit`; per-user flood cap exceeded (F-180) → skip `quota`.
7. Otherwise **send via channel adapter** (sandbox records it); on adapter error → `failed`
   + `last_error` (EC-NOT-04/F-174); on open circuit → `failed` typed `IntegrationUnavailable`.

### 4b. Outbox relay + webhook delivery — `interactors/outbox.py` / `webhook.py`
`relay_pending_events(tenant=None)`: for each `OutboxEvent(status=pending)` (abort if tenant
deactivated, EC-CEL-07): match `WebhookSubscription`s whose `event_types` include it →
create/locate a `WebhookDelivery` (UNIQUE `(subscription,event)`, idempotent, EC-CONCUR-10) →
sign payload (D7) → POST via sandbox HTTP adapter. On non-2xx/exception: `attempts++`,
schedule `next_attempt_at` per **1m/5m/30m/2h/12h**; after 5 → `dlq` (F-265/EC-INT-04/EC-CEL-08).
`replay_dlq(delivery)` re-queues. Circuit breaker wraps the HTTP adapter (D-F268).

---

## 5. Endpoint surface

**Communications** `POST/GET announcements/` (F-171, audience-validated) ·
`GET notifications/` (own log, cursor-paginated F-299) · `GET/PUT preferences/` (F-179) ·
`GET admin/delivery-status/?announcementId=` (F-174)
**Integrations** `POST/GET webhooks/subscriptions/` (F-265) ·
`POST webhooks/deliveries/{id}/replay/` (DLQ replay) · `GET jobs/{id}/` (F-302 JobRun status) ·
`GET health/` (F-015 — adapter circuit states + last success/failure)

---

## 6. Edge cases — the spec (where each is enforced)

| Code | Rule | Enforced in |
|------|------|-------------|
| **EC-NOT-01 / F-176** | SMS to deactivated user → skip + log | dispatch step 1 |
| **EC-NOT-02 / F-175** | 150 SMS/min → 100 sent, 50 queued | tenant rate-limit step 6 |
| **EC-NOT-03 / F-177** | Target role mismatch → 400 / skip role_mismatch | announcement validate + dispatch step 2 |
| **EC-NOT-04 / F-174** | MSG91 failure → log failed; admin count | adapter error → `failed` |
| **EC-NOT-05** | Absence SMS to the parent who is the marking faculty → skip `self_marked`, no dispatch | dispatch step 3 (linked_user_group_id) |
| **EC-NOT-06** | Linked faculty+parent, dual-role announcement → 1 delivered + 1 skipped `dedup` per channel | dedup_key step 5 |
| **F-179 / F-289** | User pref OR guardian-link pref off → skip `opt_out` (intersection) | dispatch step 4 |
| **F-180** | Per-user flood cap exceeded → skip `quota` | dispatch step 6 |
| **F-266 / EC-CONCUR-08** | Replay same Idempotency-Key + same body → cached response, no re-exec | idempotency mixin (D6) |
| **EC-API-01** | POST missing required Idempotency-Key → 400 | idempotency mixin |
| **F-266** | Same key + different body → 409 | idempotency mixin |
| **F-265 / EC-INT-04 / EC-CEL-08** | Subscriber 500 → retry 1m/5m/30m/2h/12h → DLQ after 5; admin DLQ count | webhook delivery backoff |
| **F-264** | Side effect written as OutboxEvent in same txn | `emit_event` inside the producer's transaction |
| **EC-CONCUR-10** | Two webhooks same event → unique `(subscription,event)`; second noop | WebhookDelivery UNIQUE |
| **F-268 / EC-AUTH-16** | 5 failures/30s → open 60s → typed IntegrationUnavailable | circuit breaker around adapters |
| **EC-INT-03** | Inbound webhook timestamp > 5 min → `replay_detected` | inbound verify (reuse fees pattern) |
| **EC-CEL-07** | Tenant deactivated mid-relay → abort, no side effect | relay tenant-status check |
| **F-269** | JobRun per-step status visible | JobRun model + `GET jobs/{id}/` |

---

## 7. Adapters (`apps/integrations/adapters/`) — sandbox-first

`sms.py` (MSG91), `email.py`, `push.py`, `webhook_http.py` — each exposes `Sandbox*` (records
into an in-memory/DB sink, deterministic, no network) and `Live*` (stub) + a `get_*()` factory
keyed on settings, exactly like `payments.get_gateway()`. Tests run in `sandbox` mode and
assert on the recorded sink + `NotificationLog` / `WebhookDelivery` rows. Live credentials are
a deploy-time swap; **no test ever touches the network**.

---

## 8. Architecture (non-negotiable)

Thin views → interactors (`@transaction.atomic`) → queries; **`.objects`/`.save()` only in
`queries/`**. Adapters are pure I/O shims (no ORM). Cross-app reads (accounts for users +
`linked_user_group_id`, organizations for tenant status, the producing modules for event
payloads) go through their query layers. Verify:
`grep -rn "\.objects\.\|\.save(" apps/communications/{views,interactors} apps/integrations/{views,interactors,adapters}` → empty.

---

## 9. File-by-file build plan

```
communications/enums.py, models/{announcement,notification}.py + migration
communications/queries/{announcement,notification}.py  (log writes, dedup lookup, counts)
communications/services/recipients.py   (resolve audience → users; pure)
communications/interactors/{notification,announcement}.py  (dispatch pipeline §4a)
communications/serializers/views/urls
integrations/enums.py, models/{infra,webhook}.py + migration
integrations/adapters/{sms,email,push,webhook_http}.py   (sandbox + factory)
integrations/queries/{webhook,job,outbox,idempotency,circuit}.py
integrations/interactors/{outbox,webhook,circuit_breaker}.py   (relay §4b)
integrations/services/idempotency.py   (mixin/helper)
integrations/serializers/views/urls   (subscriptions, deliveries replay, jobs, health)
```
Then `makemigrations communications integrations`, `migrate`, `check`, `makemigrations --check`.

---

## 10. Testing plan (every F/EC, all stubbed)

`env` fixture: tenant + branch + admin + a faculty and a parent **linked** via
`linked_user_group_id` to the same child (for EC-NOT-05/06), with prefs + a guardian link.
Tests:
- Dispatch: each §6 NOT row (inactive, rate-limit 150→100+50, role mismatch, MSG91 failure,
  **self_marked**, **dedup**, opt-out intersection, flood cap) → assert `NotificationLog`
  status/`skip_reason` + the sandbox SMS sink contents.
- Idempotency: replay same key+body → identical cached response, handler not re-run; different
  body → 409; missing key → 400.
- Webhooks: subscriber returns 500 → 5 retries on schedule → DLQ; `replay` re-queues; duplicate
  event → single delivery (UNIQUE).
- Outbox: `emit_event` inside a txn that rolls back → no OutboxEvent (transactional proof).
- Circuit breaker: 5 forced failures → open → next call returns `IntegrationUnavailable`.
- JobRun + health endpoints return expected shape.
- Full suite must stay green (currently **230**) + **zero** ORM-outside-queries.

Command unchanged:
```
export PATH="$HOME/.local/bin:$PATH" && unset USE_POSTGRES DATABASE_URL && \
DJANGO_SETTINGS_MODULE=config.settings.test python -m pytest -p no:cacheprovider -q
```

---

## 11. Build order (sub-stages) & effort

| Sub-stage | Content | Effort |
|-----------|---------|--------|
| 8.0 | Both apps: enums + models + migrations + sandbox adapters | M |
| 8.1 | Notification dispatch pipeline + all skip rules (EC-NOT-01..06, F-176/177/179/289) | **L** |
| 8.2 | Rate limit + flood cap (F-175/180, EC-NOT-02) | S |
| 8.3 | Announcements (create/target/validate) + delivery-status (F-171/174) | M |
| 8.4 | Idempotency infrastructure (F-266, EC-API-01/CONCUR-08) | M |
| 8.5 | Outbox `emit_event` + relay + transactional proof (F-264) | M |
| 8.6 | Webhook subscriptions + signed delivery + retry/DLQ + replay (F-265, EC-INT-04/CEL-08/CONCUR-10) | **L** |
| 8.7 | Circuit breaker around adapters (F-268, EC-AUTH-16) | S |
| 8.8 | JobRun + health endpoints (F-269/F-015/F-302) | S |
| 8.9 | Wire high-value emitters (absence, fee-due, result-published, payment.captured) | M |
| 8.10 | Tests (all F/EC) + full-suite green + queries scan | M |

8.1 (dispatch skip matrix) and 8.6 (webhook retry/DLQ) carry the real complexity.

---

## 12. Open decisions (confirm before building)

- **OD-1 — dispatch/relay execution.** Synchronous, in-process relay invoked on demand now,
  with a documented Celery-beat seam (**recommended**), vs. wire Celery + Redis relay now.
- **OD-2 — event-emitter coverage.** Build `emit_event` + notification triggers and wire the
  **high-value** events (absence SMS, fee-due, result-published, payment.captured,
  enrollment.created) now, leaving a documented list for the rest (**recommended**), vs. wire
  every event across all modules in this stage.
- **OD-3 — real-time delivery.** In-app notifications are **pull/poll** in Phase 1; WebSocket /
  Channels real-time push (EC-WS-*) deferred to a later stage (**recommended**), vs. stand up
  Django Channels + Redis now.
- **OD-4 — secret/PII storage.** Webhook subscription secret in a plain field behind one
  accessor now, pgcrypto encryption later (**recommended**), vs. encrypt now.

---

## 13. Risks

- **The skip matrix (§4a) is the security/correctness core** — the order matters
  (self_marked and dedup before send) and each branch must write a `NotificationLog` row.
  EC-NOT-05 (don't SMS a parent about an absence they themselves recorded as the marking
  faculty) and EC-NOT-06 (dedup a dual-role person) are the subtle ones; both need the
  `linked_user_group_id` join and explicit tests.
- **Idempotency correctness** — a replayed key must return the *cached* response without
  re-running the handler; a same-key/different-body must 409. Getting the body-hash canonical
  is the trap.
- **Webhook retry/DLQ** — the backoff schedule and the 5-attempt → DLQ transition must be
  exact, and `(subscription,event)` uniqueness prevents double-delivery across workers.
- **Transactional outbox** — `emit_event` must run inside the producer's transaction so a
  rolled-back business operation emits no event; the test proves this with a rollback.
- **Sandbox/live parity** — the sandbox adapters must mirror the live call signatures exactly,
  or the deploy-time swap breaks; keep one factory per channel, like payments.
```
