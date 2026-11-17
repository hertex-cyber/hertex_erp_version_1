# Hertex ERP — Plan Conformance Checklist

**Scope:** read-only conformance audit of `hertex-erp/` against the three root planning documents.
**Date:** 2026-07-17
**Method:** static inspection of `backend/app/**` (no app was run; `alembic/versions/` is empty so no DB exists to exercise).
**Verdict legend:** ✅ implemented · 🟡 partial / scaffolded only · ❌ absent · ⚠️ diverges from plan

> This document records *state*, not intent. Another agent owns active work in this repo; nothing here was modified.

---

## 0. Summary

| Dimension | Result |
|---|---|
| Module coverage (14+5 map) | **18 of 19 modules have models/routers** — broad scaffolding is strong |
| Cross-module wiring (the stated moat) | **1 of 4 expected integrations is real** (order→GL). PO→GL and GRN→AP are missing |
| Definition of Done (plan ground rule #5) | **0 of 18 modules meet it** — no migrations, no tests, no frontend for any module |
| Highest-leverage feature (Tally import, "the actual product" per Best-Product Plan §2.3) | ❌ **absent** |
| AI Tier 1 (forecasts/scoring, Sprint 6) | ❌ absent (`Lead.score` field exists, no scorer) |
| AI Tier 2 ("Ask Hertex", Sprint 6) | 🟡 regex intent router, **no LLM / no function calling** |
| WhatsApp as transactional channel (Sprint 5) | 🟡 webhook + bridge abstraction; **no outbound send, no Flows, no template tracking, no signature check** |

**Bottom line:** the model/API surface is ahead of schedule; the *integration, migration, AI and verification layers* the plans call non-negotiable are behind it. The plan's own bar ("if module-completion checklists are full but the four numbers are weak, effort went to the wrong places") currently applies.

> **Planning docs delivered (2026-07-17):** the 22-doc module set now exists under `docs/modules/` (00 master + 01–20 modules + 99 sequence + README). Each doc turns the ✅/🟡/❌ states below into an ordered, test-bearing implementation plan (milestones M1–M5, business-rule codes, DoD). This checklist stays the *state* snapshot; the module docs are the *fix plan*. See §15 for how the recommended order maps to `99-IMPLEMENTATION-SEQUENCE.md`.

---

## 1. Engineering ground rules (Technical Plan §0)

| # | Rule | State | Evidence |
|---|---|---|---|
| 1 | One PostgreSQL DB, one project; new modules are apps in the monolith | ✅ (stack differs, see ADR-001) | `app/db/session.py` single engine; all modules in one app |
| 2 | Every model gets `created_at`, `updated_at`, `created_by`, `tenant_id`, soft-delete | ✅ | `app/db/base.py::TenantBaseModel` — all 16 modules subclass it |
| 3 | Every app ships DRF-equivalent viewsets + OpenAPI + task file | 🟡 | Routers: ✅ (FastAPI, `/api/v1`). OpenAPI: implicit FastAPI only, no config/exposure. Task file: ❌ `app/workers/` is **empty** |
| 4 | No module talks to WhatsApp/Meta directly — all via `engage_bridge` | 🟡 partial | `integrations/service.py::send_message` exists; but it only **inserts a `ChannelMessage` row** with `status="queued"` — no HTTP call to Meta. No adapter interface classes (`ChannelAdapter`/`WhatsAppCloudAdapter`) were created |
| 5 | Definition of Done = migrations + documented DRF endpoints + RBAC + one Playwright happy-path + one demo screen | ❌ | `alembic/versions/` empty; `app/tests/` empty; `frontend/src` empty. RBAC: ✅ |

---

## 2. Sprint 0 — Platform Foundation

| Item | State | Evidence |
|---|---|---|
| `core.Role` / `Permission` / `RoleAssignment` | ✅ | `identity/models.py` — `Role`, `Permission`, `user_roles` association; `Role.approval_limit` present (plan's PO > ₹50k rule hook) |
| Field-level RBAC | 🟡 | Module+action granularity via `require_permissions`; **no field-level check** |
| `core.AuditLog` auto-hooked via signals | 🟡 | `AuditLog` model ✅, `record_audit()` ✅ — but invoked **manually** in the CRUD factory; no `pre_save`/`post_save` equivalent, so direct ORM writes bypass audit |
| Tenant scoping, `Tenant` as single source | ✅ | `deps.py`, `crud.py::tenant_scoped` |
| `core.EventBus` publish/subscribe over Redis/Celery | 🟡 | `core/events.py` is an **in-process dict of asyncio handlers**; the docstring admits Celery replacement is future work. No Redis broker |
| DoD: RBAC denial + audit + event round-trip test | ❌ | no tests exist |
| Permissions catalog + role templates | ✅ (beyond plan) | `core/permissions_catalog.py` — 13 modules, 8 role templates, single source for seeding |

---

## 3. Sprint 1 — Finance & Accounting

| Item | State | Evidence |
|---|---|---|
| `Account` | ✅ | `finance/models.py` |
| `JournalEntry` / `JournalLine` | ✅ | incl. `draft`/`posted`/`void` status |
| Double-entry validation | ✅ | `finance/service.py::_validate_lines` — debit==credit, non-zero, no dual-sided line, no negatives |
| Post locks entry | 🟡 | idempotent on already-posted; no explicit immutability guard on posted lines afterwards |
| `Invoice`, `Payment` | ✅ | incl. `source_order_id` back-link |
| `BankAccount`, `BankTransaction` | ✅ models | import/reconcile endpoints: not found (grep for CSV import) — 🟡 |
| Reports: trial balance, P&L, balance sheet, cash flow | ✅ | `finance/router.py` `/reports/*` |
| Invoice posted → auto `JournalEntry` via event bus | 🟡 **diverges** | `post_invoice_journal` is called **directly** from `sales/router.py::fulfill_order` and `pos/router.py::checkout`, not via `invoice.posted` event + listener. Works, but the plan's event-bus proof-of-concept is bypassed |
| Tally XML importer (chart of accounts + opening balances) | ❌ | `grep -i tally` → zero hits |
| DoD: DB-level double-entry enforcement, trial balance reconciles to zero, one real client COA imported | 🟡 | app-level validation only (no Postgres CHECK); reconciliation and real import: ❌ |

---

## 4. Sprint 2 — Procurement

| Item | State | Evidence |
|---|---|---|
| `Vendor`, `PurchaseRequisition`, `PurchaseOrder`, `POLine` | ✅ | `procurement/models.py` |
| `GoodsReceipt` / `GRNLine` | ✅ | — |
| `VendorInvoice` | ✅ | — |
| Three-way match (GRN qty vs PO qty, invoice vs PO total, tolerance) | ✅ | `procurement/router.py:336-351` — rejects unless fully received; 5% amount tolerance |
| Role `approval_limit` used for PO approval gate | ❌ | field exists on `Role`, never read in the PO-approve path |
| `po.approved` → notify vendor via Engage | 🟡 | event published; **no subscriber exists** |
| `grn.received` → Inventory stock-in | 🟡 | event published; stock-in is done inline in the same handler (StockMove created at `procurement/router.py:286`), not via subscriber |
| `vendor_invoice.approved` → Finance AP journal entry | ❌ | **no GL posting** on vendor invoice approval — AP is never recorded in the ledger |
| DoD: full PO→GRN→invoice→payment cycle posts correctly to Finance | ❌ | AP side of the ledger is unreachable |

---

## 5. Sprint 3 — Warehouse & Order Management

| Item | State | Evidence |
|---|---|---|
| `Warehouse`, `Bin` | ✅ | `warehouse/models.py` |
| `StockMove` as **single stock ledger** | ✅ | confirmed: no counter column anywhere; stock = `SUM(StockMove.quantity)` in `inventory/router.py:86`, `analytics/service.py:80`, `ai/service.py:45` |
| All writers go through `StockMove` | ✅ | 3 writers: procurement GRN (`:286`), sales fulfill (`:264`), POS checkout (`:196`) — no shadow tables |
| `SalesOrder` / `SalesOrderLine` | ✅ | includes `channel` (manual/pos/storefront) and `warehouse_id` |
| `DeliveryChallan` | ✅ | created on fulfill |
| Barcode-scan pick/pack endpoint | ❌ | not found |
| Order → stock decrement + Finance revenue in same request | ✅ | `sales/router.py::fulfill_order` does StockMove + Invoice + `post_invoice_journal` + audit + event |

---

## 6. Sprint 4 — POS

| Item | State | Evidence |
|---|---|---|
| POS as `SalesOrder`-equivalent with `channel=pos` | 🟡 | **separate `PosSale`/`PosSession` models** (`pos/models.py`) rather than reusing `SalesOrder`. Duplicates the order concept — a divergence from "a POS sale is just a SalesOrder" |
| Immediate fulfillment | ✅ | `pos/router.py::pos_checkout` |
| Posts to Inventory + Finance in same cycle | ✅ | StockMove + Invoice + `post_invoice_journal` (`:196-209`) |
| Offline-tolerant (queue locally, sync on reconnect) | ❌ | nothing; that was a frontend requirement and there is no frontend |
| Receipt print/share | ❌ | no frontend |

---

## 7. Sprint 5 — Engage Conversational Channel (highest-leverage sprint per plan)

| Item | State | Evidence |
|---|---|---|
| `ChannelMessage(channel, external_id, direction, contact, payload, timestamp)` | ✅ | `integrations/models.py` |
| `ChannelAdapter` interface + `WhatsAppCloudAdapter` | ❌ | no adapter classes; `send_message` is a bare row-insert |
| Webhook verifies Meta signature | ❌ | `POST /integrations/whatsapp/webhook` parses JSON and writes rows; **no `X-Hub-Signature-256` verification**, despite `META_APP_SECRET` in `config.py` |
| Webhook `GET` verify-token handshake | ✅ | `integrations/router.py:32-41` |
| `channel_message.received` on event bus | ✅ | published at `:67` |
| Modules only call `engage_bridge.send(contact, template, module_context)` | 🟡 | function exists; no module calls it yet |
| Template approval tracking (pending/approved/rejected) | ❌ | no model, no admin screen |
| WhatsApp Flows — first flow = Feedback Agent survey | ❌ | absent |
| `Contact.whatsapp_opt_in` captured at lead creation, adapter refuses if false | 🟡 | fields exist on `Contact` and `Lead` (`crm/models.py:43,63`); **no enforcement anywhere** — nothing reads the flag before sending |
| DoD: lead created → welcome template sent → inbound reply updates same lead | ❌ | no outbound send, no inbound→lead linkage (webhook only writes `ChannelMessage`) |

---

## 8. Sprint 6 — AI Tier 1 + Tier 2

| Item | State | Evidence |
|---|---|---|
| CRM lead scoring (sklearn, nightly batch) | ❌ | `Lead.score` column exists; no model, no management command, no sklearn/statsmodels in `requirements.txt` |
| Inventory reorder forecasting (moving average / exp-smoothing) | 🟡 | reorder *detection* exists (`on_hand <= reorder_level` in `ai/service.py:45`), but that is a static threshold, **not a forecast** |
| Reorder-alert dashboard | 🟡 | surfaced through analytics/AI endpoints; no dedicated dashboard |
| `POST /api/ai/ask/` natural-language query | 🟡 | `ai/router.py` + `ai/service.py::_detect_intent` — **regex keyword routing over 8 hard-coded intents**, each calling a canned ORM query |
| LLM (Claude) with function calling → scoped ORM | ❌ | `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` in config, but **zero references to anthropic/LLM** in code |
| Read-only guarantee enforced in code | ✅ (by construction) | all queries are `select()`; no write path exists — but this is because there is no LLM, not because it is guarded |
| DoD: scores update nightly, reorder dashboard, Ask Hertex answers 5 test questions | 🟡 | register-based answers only |

> Note vs. Best-Product Plan §2.4 ("AI that changes a decision"): the AI that must *pre-fill a draft PO* and *trigger a WhatsApp follow-up* is absent at both ends — no forecast to trigger from, and no working outbound channel to act through.

---

## 9. Sprint 7 — Storefront, Marketing Automation, Meta Ads

| Item | State | Evidence |
|---|---|---|
| Storefront schema / orders as `SalesOrder(channel=storefront)` | 🟡 | `channel` field exists and a `channel` filter is honoured; **no storefront module, no public catalog/cart/checkout endpoints** |
| `Campaign`, `Segment`, `CampaignSend` | ✅ models + CRUD | `marketing/models.py`, `marketing/router.py` |
| Segments are saved filters over existing tables | 🟡 | `Segment` model present; saved-filter evaluation not found |
| WhatsApp Catalog API sync (Celery task) | ❌ | absent |
| Click-to-WhatsApp → `Lead.source` attribution | ❌ | `Lead.source` field exists; no `utm`/referral capture in the webhook |
| Meta Conversions API on `order.completed` | ❌ | `order.fulfilled` event published; no outbound CAPI call |

---

## 10. Sprint 8 — BI / Documents / Assets

| Item | State | Evidence |
|---|---|---|
| `analytics.dashboard` with cross-module KPIs | ✅ | `analytics/service.py` (234 lines) — revenue, stock, receivables, pipeline |
| Materialized views + nightly Celery refresh | ❌ | live aggregate queries only; no `MATERIALIZED VIEW`, no beat scheduler |
| `Document(model_type, object_id, file)` generic FK + e-signature | ❌ | absent |
| `Asset` + monthly depreciation → journal entry | ❌ | absent (also listed "adequate-bar" in Best-Product Plan §3) |

---

## 11. Sprint 9 — LMS

❌ absent entirely (also "adequate-bar"; resequenced to Phase 4 in the strategic plan).

---

## 12. Sprint 10 — Automation Engine + AI Tier 3

❌ absent. No `WorkflowRule`, no rule-builder, no agentic action layer.
Note: the event names this sprint depends on are **already published** (`order.created`, `order.fulfilled`, `pos.sale.completed`, `po.approved`, `grn.received`, `channel_message.received`, `ticket.message.created`) — but **there is not a single `@subscribe` handler in the codebase**, so the bus currently has no consumers at all.

---

## 13. Additional modules from the strategic plan §2

| Module | State |
|---|---|
| Order Management | ✅ `sales/` |
| Customer Support / Helpdesk | ✅ `support/` (Ticket, TicketMessage, event on message create) |
| Project & Work Management | ✅ `projects/` (Project, Task) — light, not the money-aware WorkItem design |
| Settings / number sequences | ✅ `settings/` (AppSetting, NumberSequence) |
| GST / e-invoicing (IRN, e-way bill, GSTR) | ❌ `Product.hsn_code`, `tax_rate` fields only |
| Asset Management | ❌ |
| Document Management | ❌ |
| LMS | ❌ |
| Manufacturing | ❌ (intentionally deferred by plan) |

---

## 14. Divergences that need a decision (not defects)

1. **Stack:** FastAPI + SQLAlchemy 2.0 async replaces the plan's "Django 5.2 monolith". Single-Postgres principle preserved; the plan's competing-backend risk is not resolved. → see `docs/adr/ADR-001-fastapi-over-django.md`
2. **POS duplicates `SalesOrder`** instead of reusing it with `channel=pos`, which was an explicit plan instruction. Risk: a second order code path to keep in sync with Finance/Inventory. **Resolved in planning (module 06, decision D1):** POS checkout already creates a real `SalesOrder(channel="pos")` linked via `PosSale.sales_order_id`; `PosSale` stays a thin terminal wrapper, no merge required.
3. **Invoice→GL posting is direct-call, not event-driven.** Correct output, but it removes the single-database "event bus proof" the plan wanted and means the bus has no consumers.
4. **"Ask Hertex" is regex, not LLM.** Cheaper and safer to start, but it is not the Tier 2 capability the plan sells; and the extraction library (sklearn/statsmodels) that Tier 1 requires is not yet a dependency.

---

## 15. Recommended order of work (highest plan-leverage first)

1. **Alembic baseline + one test per module** — nothing else can be trusted until migrations and the DoD test exist (unblocks every Sprint).
2. **Tally importer (chart of accounts + opening balances)** — Best-Product Plan §2.3 calls this "the actual product, not a feature of Finance".
3. **Vendor-invoice → AP journal posting** — closes the AP side of double-entry; currently the ledger cannot represent payables.
4. **Real outbound WhatsApp send + signature verification + consent enforcement** — Best-Product Plan §2.2 is unreachable without an actual send path.
5. **Wire at least one `@subscribe` handler** on `invoice.posted`/`order.fulfilled` so the event bus proves the single-database thesis instead of idling.
6. **Reorder *forecast* (statsmodels) + draft-PO pre-fill** — the one AI feature the Best-Product Plan says must change a decision.

---

## 16. What this audit did not cover

- No app was started, no tests run, no DB created (impossible: no migrations).
- FastAPI's implicit OpenAPI output was not generated or read.
- `frontend/src` and `docs/` are empty, so no UI or architecture doc could be compared.
- Behaviour of `_validate_lines`, three-way match and stock math was verified by reading, not by exercising.
