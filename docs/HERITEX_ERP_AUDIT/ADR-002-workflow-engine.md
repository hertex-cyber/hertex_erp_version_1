# ADR-002 — Automation / Workflow Engine: Build vs Adopt

**Status:** Proposed
**Date:** 2026-07-17
**Deciders:** tech lead, product owner (D2 in `docs/modules/00-MASTER-ARCHITECTURE.md §12`)
**Blocks:** module 03 M-append-only (I2 enforcement through a controlled write path), module 14 M4 (AI Tier 3 action layer), master §9 event consumers.

---

## Context

Three planned capabilities all need the same thing: a way to express **"when event X happens, do action Y, with approval/policy"** — deterministically, audited, and safe:

1. **Event subscribers** — the master architecture (§9) defines 13 domain events (`invoice.posted`, `order.fulfilled`, `stock.low`, `po.approved`, …). Today `app/core/events.py` is an in-process `asyncio` fan-out with **zero subscribers** (verified: no `@subscribe` handler exists in the codebase; `grep -r "@subscribe" backend/app` → none). The bus proves nothing because nothing consumes it.
2. **AI Tier 3 actions** — module 14 M4 requires a `draft_po` / `draft_whatsapp_followup` action that is *proposed → approved → executed* with idempotency and audit (`ai_actions` table, rules AI-03/AI-06).
3. **Approval chains** — module 02 requires PO approval to read `Role.approval_limit` (currently never read; the ₹50k CFO rule in the plan is unimplemented).

The question: **build a lightweight rule/action engine in-house, or adopt an existing workflow/orchestration product?**

## What already exists (constraint)

- `app/core/events.py` — in-process pub/sub, no persistence, no retry, no subscribers.
- `celery==5.6.1` + `redis==6.4.0` are **in `requirements.txt` but no tasks or workers exist** (`app/workers/` empty).
- Single-Postgres monolith is a hard principle (Technical Plan §0 rule #1).
- Everything must be tenant-scoped and audited (I6).

## Options

### Option A — Build a minimal in-house rule engine on Celery + Postgres
A `workflow_rules` table (`trigger_event`, `condition_json`, `action_type`, `policy_json`), a Celery beat + subscriber dispatcher, an `action_handlers` registry, and an `outbox` table for reliable at-least-once delivery.

- **Pros:** single DB, no new service, tenant-scoped by construction, full control over audit and approval semantics, exact fit for AI Tier 3 (`action_registry` is the same abstraction). Small surface (~6 tables, one dispatcher).
- **Cons:** we build retry/idempotency/scheduling ourselves (well-understood, ~1–2 engineer-weeks); must keep it simple enough not to become a workflow *product*.

### Option B — Adopt a workflow/orchestration product (Temporal / Prefect / Airflow)
- **Pros:** battle-tested retries, durable timers, observability.
- **Cons:** a **second stateful service** (Temporal server, or Prefect/Airflow scheduler) violates the single-DB/single-service principle; AI Tier 3 actions need *approval-gated business actions*, not DAG scheduling — the fit is poor; operational overhead for an SMB ERP is disproportionate. Overkill for 13 event types and ≤20 actions.

### Option C — Adopt a BPMN engine (Camunda / Flowable)
- **Pros:** standard process notation, approval semantics built-in.
- **Cons:** JVM sidecar service, heavy for this scale, poor fit with the FastAPI/async stack, and BPMN is a design surface we do not need (our flows are event→condition→action, not arbitrary human process diagrams).

### Option D — Do nothing / ad-hoc per-module calls
- **Cons:** this is the current state; it is exactly why the bus has no subscribers and AP posting is a direct call with no fan-out. Rejected — it is the problem, not a solution.

## Decision

**Adopt Option A — build a minimal workflow/action engine on Celery + Postgres**, scoped deliberately small:

```
workflow_rules     trigger_event, condition_json (declarative, no code), action_type, policy_json,
                   is_active, tenant_id
workflow_runs      rule_id, event_payload_json, status [pending|running|succeeded|failed],
                   attempts, last_error, started_at, finished_at
outbox             event_name, payload_json, published_at, consumed_at   (reliable dispatch)
action_registry    action_type -> handler (python), scope (permission code), is_idempotent
ai_actions         (module 14) — reuses the same propose/approve/execute semantics
```

**Rules of the engine (binding):**
- Conditions are **declarative JSON** (`{"field": "...", "op": "gt", "value": 50000}`), never executable code (no eval).
- Actions are **registered code handlers**, not user-supplied scripts; each declares its required permission and idempotency key.
- Delivery is **at-least-once** via the `outbox` table + Celery; handlers must be idempotent (dedupe on `(rule_id, event_id)`).
- Approval-gated actions (Tier 3, PO over limit) go `proposed → approved → executed` with `actor_user_id` + `on_behalf_of` (I6).
- Every run is audited; failures go to a dead-letter view, never silently dropped.

**Celery is retained** (already a dependency) as the execution vehicle — this ADR only mandates that it gains a **worker + beat + the dispatcher task**, closing the "0 workers" gap in `99-IMPLEMENTATION-SEQUENCE.md Phase 0`.

## Consequences

- **Positive:** closes the "event bus has no consumers" gap; unblocks AI Tier 3 (`action_registry` = same abstraction); makes `approval_limit` enforceable; stays one DB, one deployable.
- **Positive:** Phase 0.3/0.4 of the master sequence become concrete (worker + first subscriber).
- **Negative:** we own retry/observability of the dispatcher — mitigated by the outbox table and simple metrics (runs succeeded/failed, dead-letter depth).
- **Sequencing:** this ADR should be **accepted before Phase 1.6** (append-only stock write path) and **before module 14 M4** (AI actions), per the master sequence dependency graph.

## Alternatives rejected (summary)

| Option | Verdict | Why |
|---|---|---|
| A — in-house on Celery+PG | **chosen** | single DB, right size, fits AI Tier 3, tenant-scoped |
| B — Temporal/Prefect/Airflow | rejected | second stateful service; wrong fit for approval-gated business actions |
| C — BPMN (Camunda/Flowable) | rejected | JVM sidecar, heavy, unneeded process-design surface |
| D — per-module ad-hoc | rejected | current state; proven to leave the bus empty and AP posting ad-hoc |

## Follow-ups

- [ ] Accept/refine this ADR in review.
- [ ] Add `workflow_rules`, `workflow_runs`, `outbox`, `action_registry` tables (Alembic, Phase 0).
- [ ] Wire the Celery worker + beat + dispatcher task; register the first subscriber (`invoice.posted` → audit/analytics).
- [ ] Encode the PO `approval_limit` rule as the first `workflow_rules` row (proves the engine against a real plan requirement).
- [ ] Reuse the engine for AI Tier 3 actions (module 14 M4).