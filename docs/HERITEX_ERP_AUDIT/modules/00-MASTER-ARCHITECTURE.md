# 00 — Master Architecture & Module Framework

**Project:** Hertex Business Suite
**Audience:** engineering, product, CTO
**Status:** normative — module documents inherit the invariants here and must not contradict them
**Date:** 2026-07-17
**Companions:** `Hertex-Best-Product-Plan.md`, `Hertex-ERP-End-to-End-Implementation-Plan.md`, `Hertex-ERP-Technical-Implementation-Plan.md`, `../PLAN-CONFORMANCE-CHECKLIST.md`, `../adr/ADR-001-fastapi-over-django.md`

---

## 1. Purpose of this document

Every module plan in `docs/modules/` is written to a shared frame. Without one, twenty-two documents drift: Finance invents a different tenant rule, Inventory disagrees with POS about what "stock" means, and the single-database advantage — the only structural moat we have against Zoho — quietly disappears.

This document fixes, once:

1. The **invariants** that no module may break (§3).
2. The **canonical entity ownership map** (§4) — which module owns which table, so we never create two versions of "customer".
3. The **document/state-machine conventions** (§5) every transactional module follows.
4. The **event catalogue** (§6) so integration is by publication, not by import.
5. The **benchmarking framework** (§7) used in every module doc to compare against Zoho / SAP / Odoo / Tally.
6. The **document template** (§8) every module doc must fill, and the **Definition of Done** (§9).
7. **AI capability tiers** (§10) applied consistently per module.
8. **Cross-cutting non-functionals** (§11): security, PDPD, audit, performance, multi-tenancy.

---

## 2. Current baseline (verified 2026-07-17)

Established by direct inspection; module docs must plan *from* this, not from an imagined system.

| Fact | Value |
|---|---|
| Backend modules present | 18 directories under `backend/app/modules/` |
| Tables defined | **52** across the ORM |
| Migrations | **0** (`alembic/versions/` empty) |
| Tests | **0** (`app/tests/` empty) |
| Background workers | **0** (`app/workers/` empty) |
| Event subscribers | **0** — seven events are published, none consumed |
| Frontend | **0 files** (`frontend/src` empty) |
| Stack | FastAPI 0.128, SQLAlchemy 2.0 async, asyncpg, Alembic, Pydantic v2, Celery (configured, unused), Redis |
| Auth | JWT access+refresh, `token_version` revocation, bcrypt |
| RBAC | Module+action granularity, 8 role templates, `permissions_catalog.py` is the single source of truth |
| Multi-tenancy | Row-level `tenant_id`, enforced in `crud.py::tenant_scoped` |

**Consequence:** no module is production-viable. Every module doc must include a "path from current state" section, and no doc may assume migrations or tests already exist.

---

## 3. Invariants (non-negotiable, all modules)

These six rules are the product. A module that violates one is rejected in review regardless of feature completeness.

### I1 — One database, one schema, one owner per table
No module creates a second table for an entity another module owns. If Sales needs customers, it uses `customers` (owned by Sales). If Procurement needs products, it uses `inventory_products`. Cross-module needs are satisfied by FK + service call + event, never by copy.
*Why:* this is the Zoho/SAP fragmentation defence (`Best-Product-Plan §2.1`). Zoho's quote-vs-books sync gap exists because CRM and Books each own a copy.

### I2 — Stock is a sum of moves, never a stored counter
`on_hand(product, warehouse) = SUM(StockMove.quantity)`. There is no `quantity_on_hand` column anywhere, ever. Every physical change writes a `StockMove` row with a `movement_type`, `reference`, and `unit_cost`.
*Why:* avoids the entire "inventory drift" bug class; matches the direction Odoo has moved to (`stock.move`-carried value, valuation layer removed in the 2025 refactor).

### I3 — Money is double-entry or it does not exist
No module may affect financial state except by posting a balanced `JournalEntry`. Invoices, payments, GRNs, POS sales and payroll all resolve to journal lines. `SUM(debit) = SUM(credit)` is enforced both in application validation and (target) a Postgres constraint trigger.
*Why:* an ERP whose ledger can be bypassed is a spreadsheet with a UI.

### I4 — Documents are immutable once posted; corrections are reversals
A posted `JournalEntry`, issued `Invoice`, approved `PurchaseOrder`, completed `PosSale` and dispatched `DeliveryChallan` are never edited in place. Correction = a new document of reversing/adjusting type referencing the original.
*Why:* audit trail credibility (`SAP-grade`), and GST requires it (credit/debit notes are first-class documents).

### I5 — Every document declares its own lifecycle
Each transactional entity has an explicit `status` field with a documented state machine (§5) and a guard on every transition. No boolean flags standing in for states (`is_approved`, `is_done` are banned).

### I6 — Tenancy and audit are enforced at the framework layer
`tenant_id` scoping happens in `crud.py`/`deps.py`, not per-module. `AuditLog` is written for every state transition, including transitions performed by background jobs and agents. An AI action is audited with the acting user's identity plus an `on_behalf_of` marker.

---

## 4. Canonical entity ownership map

52 tables, assigned to exactly one owning module. "Reads" means FK-eligible; "writes" means the module may mutate it.

| Entity (table) | Owner | Modules that read | Modules that write | Cross-module mutation rule |
|---|---|---|---|---|
| `tenants`, `users`, `roles`, `permissions` | Identity | all | Identity | None — Identity only |
| `audit_logs` | Identity | — | all (via `record_audit`) | Append-only |
| `app_settings`, `number_sequences` | Settings | all | Settings | Numbers requested via `next_number()` |
| `inventory_products`, `inventory_categories` | Inventory | all | Inventory | Price changes via event `product.price_changed` |
| `inventory_stock_moves` | Inventory | all | Inventory (append-only) | Any module may *request* a move via service API |
| `warehouses`, `warehouse_bins` | Warehouse | all | Warehouse | — |
| `customers` | Sales | Finance, POS, CRM | Sales | Customer creation from a won Deal via `deal.won` |
| `sales_orders`, `sales_order_lines`, `sales_delivery_challans` | Sales | Finance, Inventory | Sales | Fulfilment posts stock + invoice |
| `procurement_vendors`, `procurement_requisitions`, `procurement_purchase_orders`, `procurement_po_lines`, `procurement_goods_receipts`, `procurement_grn_lines`, `procurement_vendor_invoices` | Procurement | Finance, Inventory | Procurement | Vendor invoice approval must post AP |
| `finance_accounts`, `finance_journal_entries`, `finance_journal_lines` | Finance | Analytics | Finance | **Append-only via posting service** |
| `finance_invoices`, `finance_payments` | Finance | Sales, POS, Procurement | Finance | Every module's invoice resolves here |
| `finance_bank_accounts`, `finance_bank_transactions` | Finance | — | Finance | Reconciliation only |
| `pos_sessions`, `pos_sales`, `pos_sale_lines` | POS | Finance, Inventory | POS | **To be merged into order model — see §12** |
| `crm_companies`, `crm_contacts`, `crm_leads`, `crm_deals`, `crm_activities` | CRM | Sales, Marketing | CRM | Deal won → Sales customer |
| `hr_departments`, `hr_employees`, `hr_attendance`, `hr_leave_requests`, `hr_payroll_runs`, `hr_payslips` | HR | Projects, Finance | HR | Payroll run posts a journal entry |
| `projects`, `project_tasks` | Projects | HR, Analytics | Projects | Billable time → invoice line |
| `support_tickets`, `support_ticket_messages` | Support | CRM, Integrations | Support | Ticket resolution may reduce invoice? no — credit note only |
| `marketing_campaigns`, `marketing_segments`, `marketing_campaign_sends` | Marketing | CRM | Marketing | Segments are saved filters, not copies |
| `channel_messages` | Integrations | CRM, Support, Sales | Integrations | The only writer of external channel state |

**Rejected patterns:** a `crm_customers` table (CRM uses Sales' `customers`), a `StockBalance`/`StockCache` table (I2), an `InvoiceHeader` duplicate per module (I3), a per-module `attachments` table (use Documents module).

---

## 5. Document conventions

### 5.1 Mandatory fields on every transactional entity
```
id          UUID PK
tenant_id   UUID FK -> tenants      (indexed, non-null for tenant data)
created_at, updated_at
created_by_id, updated_by_id        (who + who last changed)
status      explicit enum/state machine
number      human-facing doc number, unique per tenant (Settings.next_number)
is_active   soft delete (master data only — never on posted documents)
```

### 5.2 State machine standard

Every document carries a transition table, published in its module doc in this exact shape:

```
state        --event-->      next_state     guard                          side effects
draft        submit          pending        lines non-empty, totals valid  audit
pending      approve         approved       approver.limit >= total         audit, journal, event
approved     cancel          cancelled      nothing fulfilled              reversal JE
```

Rules: terminal states are terminal (`posted`, `cancelled`, `void`); every guard is a named predicate tested in a unit test; every transition writes an audit row; every transition that changes money or stock emits an event.

### 5.3 Numbering
`Settings.number_sequences` is the *target*; the current `core/numbering.py` derives count+1, which is unsafe under concurrency and leaves gaps on rollback. Every module doc that uses numbers must plan the sequence-table migration.

### 5.4 Money
`Numeric(14,2)` for amounts, `Numeric(14,3)` for quantities (lets us support grams/ml), currency code stored on the document, never assumed INR. Rounding policy declared per module; GST rounding at document level (not line level) to match IRP validation.

---

## 6. Event catalogue

Events are the integration contract (Technical Plan §6–7). Current state: seven publishers, zero subscribers.

| Event | Publisher | Payload | Target subscribers | Status |
|---|---|---|---|---|
| `invoice.posted` | Finance | invoice_id, tenant_id, total, tax | Procurement(AP mirror), Analytics, Integrations | **structured, not emitted** |
| `invoice.paid` | Finance | invoice_id, payment_id, amount | CRM (deal close), Analytics | planned |
| `order.created` | Sales | order_id, total, channel | Inventory (reserve), Integrations | published |
| `order.fulfilled` | Sales | order_id, invoice_id, total | Finance, Marketing (CAPI), Analytics | published |
| `po.approved` | Procurement | po_id, total, vendor_id | Integrations (vendor notice), Finance (commitment) | published |
| `grn.received` | Procurement | grn_id, po_id | Inventory, Finance (GRNI accrual) | published |
| `vendor_invoice.approved` | Procurement | vendor_invoice_id, po_id, amount | **Finance (AP journal)** — missing | planned |
| `stock.low` | Inventory | product_id, warehouse_id, on_hand, reorder_level | Procurement (draft PO), Integrations | planned |
| `channel_message.received` | Integrations | channel, count | CRM (link to lead), Support (ticket) | published |
| `pos.sale.completed` | POS | sale_id, total | Finance, Inventory, Analytics | published |
| `ticket.message.created` | Support | ticket_id, message_id | Integrations (notify), Analytics | published |
| `deal.won` | CRM | deal_id, amount, customer_id | Sales (create customer), Finance | planned |
| `payroll.processed` | HR | run_id, total, journal_entry_id | Finance | planned |

**Architecture decision required:** the in-process `core/events.py` bus has no durability and no subscribers. Target is Redis/Celery with an outbox table (transactional outbox pattern) so an event is only published if the transaction commits. Every module doc must state which of its events route through the outbox.

---

## 7. Benchmarking framework (used in every module doc)

Comparison is only meaningful against the competitor a Kerala SMB actually evaluates (`Best-Product-Plan §1`). Each module doc fills this table with *specific*, checkable claims.

| Benchmark | What we compare | Why it matters to our buyer |
|---|---|---|
| **Tally + Excel + WhatsApp** | Data-entry friction, migration import, GST docs | The default; we must beat it on re-entry, not features |
| **Zoho One** | Cross-app sync gaps, price, per-seat cost, module depth | Our moat is their structural weakness |
| **SAP Business One** | Process discipline: approval chains, audit, COA rigour | Credibility benchmark for enterprise-grade claims |
| **Odoo 17/18** | Modelling quality: stock moves, valuation, accounting | Closest open-source architectural peer; free reading of their mistakes |
| **NetSuite / Dynamics 365 BC** | Multi-entity, reporting depth | Only relevant for upper-SMB deals |

Each module doc produces:
- **Table stakes** — must exist or buyer rejects us (parity with Tally/Zoho).
- **Differentiators** — where we beat them, with the demo that proves it.
- **Deliberately not competing** — named, per `Best-Product-Plan §3` (e.g. HR payroll UX, BI visualisation).
- **Known competitor strengths we will not match in v1** — stated honestly.

---

## 8. Module document template (mandatory sections)

Each file `NN-<MODULE>.md` contains, in this order:

1. **Purpose & scope** — what the module is, what it is *not*.
2. **Current state** — tables/models/endpoints that exist today, line-referenced, plus gaps.
3. **Domain model** — entities, relationships, key fields, constraints, indexes, invariants specific to the module.
4. **State machines** — per document, per §5.2 format.
5. **API surface** — resource list, verbs, permission codes, pagination/filtering, error taxonomy.
6. **Business rules** — numbered, testable statements (`BR-01`, `BR-02`, …).
7. **Workflows (end-to-end)** — the critical journeys, step by step with the invariants each step touches.
8. **Accounting/stock/ledger impact** — exactly which journal lines or stock moves are created, when.
9. **Benchmarks** — §7 table filled, plus a parity gap list.
10. **AI capabilities** — Tier 1/2/3 per §10, with the *decision* it changes and the guardrail.
11. **Non-functional** — performance targets, concurrency/locking, idempotency, data volume, retention.
12. **Security & compliance** — RBAC codes, field-level rules, GST/DPDP obligations, audit points.
13. **Reporting & analytics** — KPIs, materialised views, reconciliation reports.
14. **Integrations** — inbound/outbound events, external APIs (IRP, WhatsApp, Razorpay, bank feeds).
15. **Implementation plan** — phased milestones with acceptance criteria, ordered dependencies, estimated effort.
16. **Test plan** — unit/invariant tests, integration tests, Playwright happy path, failure injections.
17. **Migration & rollout** — Tally import path, data cutover, backfill, feature flags.
18. **Risks & open questions** — explicit, with owner-type (not person).
19. **Definition of Done** — §9 checklist, ticked or explicitly waived with reason.

---

## 9. Definition of Done (per module)

Inherited from Technical Plan ground rule #5, made concrete:

- [ ] Alembic migration(s) created, reversible, applied from empty DB
- [ ] Every model field documented; every FK indexed; every state guard covered by a test
- [ ] All invariant tests green (I1–I6 have at least one test each where the module touches them)
- [ ] Permission codes registered in `permissions_catalog.py` with role templates updated
- [ ] Audit rows written on every transition (test asserts it)
- [ ] Events published through the outbox; at least one subscriber integration-tested
- [ ] OpenAPI schema generated and checked for breaking changes
- [ ] Idempotency verified for every POST (double-submit test)
- [ ] One Playwright happy path end-to-end
- [ ] One demo screen in the React shell
- [ ] Performance: list endpoints p95 < 300 ms at 100k rows for the module's largest table
- [ ] Runbook: deployment, rollback, and one reconciliation report
- [ ] Conformance row updated in `../PLAN-CONFORMANCE-CHECKLIST.md`

---

## 10. AI capability tiers (consistent vocabulary)

Following Technical Plan §8 and `Best-Product-Plan §2.4`, with the standing rule that **AI must change a decision, not summarise data**.

| Tier | Name | Definition | Latency budget | Write access | Examples |
|---|---|---|---|---|
| **1** | Embedded intelligence | Per-module model producing a ranked/scored signal surfaced in the UI at the decision point | batch/nightly, or <200 ms inline | **none** — suggests only | lead score, reorder forecast, anomaly flag, attrition risk, ticket priority |
| **2** | Conversational interface | "Ask Hertex": NL → scoped read-only query | <3 s | **read-only, enforced** | "outstanding receivables from X", "stock below reorder" |
| **3** | Agentic action | Agent performs a write through a **pre-approved, narrowly-scoped action type** in the workflow engine, always audited, always human-approvable | <10 s | scoped, audited, reversible | draft PO on low stock, draft WhatsApp follow-up on stale deal, reconcile bank lines |

Standing AI rules:
- **A1 — Never trust model output for authorisation.** Tenant/RBAC scoping is applied by code after the model's choice, never inside it.
- **A2 — No raw SQL from a model.** ORM query objects only, built from an allow-listed intent map.
- **A3 — Every Tier 3 action is a workflow-engine action type**, so it inherits approval chains, audit and reversal (Technical Plan §12).
- **A4 — Explainability:** every Tier 1 score exposes its top 3 contributing features.
- **A5 — Cost guard:** per-tenant token budget; batch models preferred over LLM calls for tabular problems.

---

## 11. Cross-cutting non-functionals

**Security:** JWT with `token_version` revocation; bcrypt; permission codes checked at router level; field-level redaction for salary, bank details and GST credentials; audit on all writes.
**India compliance:** DPDP Act 2023 — consent capture, purpose limitation, data-principal rights (access/correction/erasure), breach notification; WhatsApp opt-in is a legal requirement not a UX nicety (Meta treats us as a processor); GST e-invoicing obligations per module 17.
**Multi-tenancy:** row-level `tenant_id` today. Decide and record: row-level vs schema-per-tenant for large clients (row-level is right until a client demands physical isolation).
**Performance budgets:** list p95 < 300 ms; document p95 < 500 ms; POS checkout p95 < 800 ms (cashier waiting); reports < 5 s or asynchronous with job status.
**Idempotency:** all POSTs accept `Idempotency-Key`; retries must not double-post journals or stock.
**Concurrency:** optimistic locking (`version` column) on documents; `SELECT … FOR UPDATE` on stock reservation and journal posting.
**Retention:** financial documents 8 years (Companies Act), audit logs 8 years, channel messages 2 years, soft-deleted masters 90 days then purge.
**Observability:** every request trace-ID; every event logged with correlation ID; module-level metrics (documents created, transitions, failures).

---

## 12. Known architectural decisions pending

Carried forward, each blocking at least one module doc:

| # | Question | Blocks | Recommendation |
|---|---|---|---|
| D1 | Merge `pos_sales` into `sales_orders`? | 06-POS, 05-SALES | **Resolved — no merge needed.** Verified: POS checkout already creates a real `SalesOrder(channel="pos")` and links `PosSale.sales_order_id` (`pos/router.py:136-156`). `PosSale` stays as a thin terminal wrapper (cash drawer, tendered/change, offline sync), the ledger lives on `SalesOrder`. |
| D2 | Event bus: in-process → Celery + transactional outbox? | all integration sections | **Resolved — build a minimal in-house engine on Celery+Postgres; see `docs/adr/ADR-002-workflow-engine.md`.** Outbox table before any cross-module automation; no Temporal/BPMN sidecar (single-DB principle). |
| D3 | `number_sequences` adoption (row-locked) vs current count+1 | every document with a number | **Yes** — current scheme is unsafe under concurrency |
| D4 | Field-level RBAC implementation | 08-HR (salary), 16-IDENTITY | Attribute-level policy on serializers |
| D5 | Valuation method: no valuation layer (Odoo's new direction) vs weighted-average layer table | 03-INVENTORY, 01-FINANCE | Start with `unit_cost` on StockMove + periodic valuation; do not build a layer table |
| D6 | Storefront included in v1? | 05-SALES, 19 | Defer per phase plan; schema hook only (`channel`) |
| D7 | Manufacturing scope | 03-INVENTORY | Out of scope, per Best-Product Plan §3 |

---

## 13. Reading order

1. `01-FINANCE.md` — the ledger everything else posts to.
2. `02-PROCUREMENT.md`, `03-INVENTORY.md`, `04-WAREHOUSE.md` — procure-to-pay and the stock ledger.
3. `05-SALES.md`, `06-POS.md` — order-to-cash.
4. `07-CRM.md`, `08-HR.md`, `09-PROJECTS.md` — demand and people.
5. `10-SUPPORT.md`, `11-MARKETING.md`, `12-INTEGRATIONS.md` — channels.
6. `13-ANALYTICS.md`, `14-AI.md`, `15-SETTINGS.md`, `16-IDENTITY.md` — platform.
7. `17-GST-EINVOICING.md`, `18-TALLY-MIGRATION.md`, `19-DOCUMENTS.md`, `20-ASSETS.md` — compliance and the missing moat features.
8. `99-IMPLEMENTATION-SEQUENCE.md` — the only place module ordering is decided.

---

## 14. How these documents will be trusted

A module doc is only useful if it is true. Therefore:

- Every "current state" claim must cite a file path (and line where practical).
- Every competitor comparison must name the concrete behaviour, not "better UX".
- Every plan item must be either *already built*, *planned with a phase*, or *explicitly out of scope* — no silent gaps.
- Where research could not confirm a fact (e.g. a search timed out), the doc must say `UNVERIFIED` rather than assert.

Research status as of 2026-07-17:
- **Tally XML** — now **verified** from official Tally developer docs (envelope tags, port 9000, inverted sign convention, zero-sum requirement, `CREATED`/`ERRORS` response). Grounded in `18-TALLY-MIGRATION.md §3`; no longer `UNVERIFIED`.
- **GST 2.0** — verified (22 Sep 2025: 12%/28% slabs abolished → 0/5/18/40; e-invoicing ≥₹5 Cr; 30-day IRP window ≥₹10 Cr; e-way bill >₹50,000). Grounded in `17-GST-EINVOICING.md §3`.
- **SAP B1 table-level detail** — still `UNVERIFIED` (not load-bearing; module docs compare SAP at behaviour level only). Marked in §9 of the relevant modules; no re-search needed for build.
