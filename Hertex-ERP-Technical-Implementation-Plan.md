# Hertex Business Suite — Technical End-to-End Implementation Plan
### Sprint-by-sprint build plan: schema, APIs, AI, WhatsApp/Meta, deployment

This is the execution-level companion to the strategic module/roadmap plan — it breaks each phase into concrete sprints with data models, API surfaces, integration steps, and Definition-of-Done, so the team can pick it up and start building against the existing Django 5.2 / React 19 / PostgreSQL / single-shared-database stack.

---

## 0. Engineering Ground Rules (apply to every sprint below)

1. **One PostgreSQL database, one Django project.** New modules are new Django apps (`finance/`, `procurement/`, `warehouse/`, `pos/`, `marketing/`) inside the existing monolith — never a separate service or separate schema unless Section 7 (Engage/HertexFlow boundary) explicitly says so.
2. **Every model gets:** `created_at`, `updated_at`, `created_by`, `tenant_id` (or org FK), and soft-delete (`is_active`) — required for the RBAC/audit-trail work in Sprint 1.
3. **Every new app ships with:** Django REST Framework viewsets, OpenAPI schema (drf-spectacular or similar), and a Celery task file even if empty — keeps the async/event pattern consistent for Section 6's event bus.
4. **No module talks to WhatsApp/Meta directly.** Everything goes through the `engage_bridge` interface defined in Sprint 6 — this is the single most important rule for avoiding the Zoho-style fragmentation this whole plan is designed to avoid.
5. **Definition of Done for every module** = migrations applied, DRF endpoints documented, RBAC rules registered, one Cypress/Playwright happy-path test, one demo-able screen in the existing React shell.

---

## 1. Sprint Map at a Glance

| Sprint | Weeks | Focus | Depends on |
|---|---|---|---|
| 0 | 1–2 | Platform foundation: RBAC, audit trail, tenant scoping, event bus skeleton | — |
| 1 | 3–5 | Finance & Accounting core (GL, AP/AR, bank recon) | Sprint 0 |
| 2 | 5–7 | Procurement (PO, vendor, 3-way match) | Sprint 1 (posts to GL) |
| 3 | 6–8 | Warehouse + Order Management (parallel to Sprint 2) | Existing Inventory |
| 4 | 8–9 | POS | Sprint 1, 3 |
| 5 | 9–10 | Engage Conversational Channel abstraction (WhatsApp Cloud API adapter) | Existing Engage stack |
| 6 | 10–12 | AI Tier 1 (CRM scoring, Inventory forecasting) | Sprint 3, existing CRM |
| 7 | 12–14 | Storefront go-live + Marketing Automation + Meta Ads/Conversions API | Sprint 3, 5 |
| 8 | 14–16 | BI/Analytics dashboards, Document Mgmt + e-signature, Asset Mgmt | All prior |
| 9 | 16–18 | LMS (internal-first) | Sprint 0 only |
| 10 | 18+ | No-code Automation Engine + AI Tier 3 (agentic) | Sprint 6, validated by 2–3 clients |

---

## 2. Sprint 0 — Platform Foundation (Weeks 1–2)

**Goal:** every module built afterward inherits security, auditability, and tenant isolation for free.

**Build:**
- `core.Role`, `core.Permission`, `core.RoleAssignment` models; DRF permission classes that check module + field-level access.
- `core.AuditLog` — generic model capturing `(actor, action, model, object_id, diff_json, timestamp)`; hook via Django signals (`pre_save`/`post_save`) so every app gets it automatically, no per-app boilerplate.
- Confirm/extend tenant scoping: if Engage is already multi-tenant, reuse its `Tenant`/`Organization` model as the single source; every new app FKs to it.
- `core.EventBus` — thin wrapper around Celery: `publish(event_name, payload)` / `@subscribe(event_name)` decorator. Start with Postgres-backed Celery broker (Redis already in use for Engage) — no Kafka yet.

**Definition of Done:** a test model in a scratch app demonstrates RBAC denial, an audit log entry, and one event publish/subscribe round trip.

---

## 3. Sprint 1 — Finance & Accounting Core (Weeks 3–5)

**Data model (new `finance` app):**
```
Account(code, name, type[asset/liability/equity/income/expense], parent, is_active)
JournalEntry(date, reference, memo, created_by, status[draft/posted/void])
JournalLine(journal_entry FK, account FK, debit, credit)
Invoice(customer FK, number, date, due_date, status, currency, total)   # extends existing GST Invoicing
Payment(invoice FK, amount, method, date, reference)
BankAccount(name, account_number, bank_name, opening_balance)
BankTransaction(bank_account FK, date, amount, description, matched_journal_line FK nullable)
```

**Key APIs:**
- `POST /api/finance/journal-entries/` (draft), `POST .../{id}/post/` (locks the entry, validates debit=credit)
- `GET /api/finance/reports/trial-balance/`, `.../profit-loss/`, `.../balance-sheet/`, `.../cash-flow/`
- `POST /api/finance/bank-transactions/import/` (CSV/bank-feed ingest) + `.../reconcile/` (match against JournalLine)

**Integration points:**
- Existing GST Invoicing module: every posted invoice auto-creates a `JournalEntry` (AR debit / Revenue credit) via the event bus (`invoice.posted` → finance listener) — this is the first real proof of the single-database thesis.
- Tally import/export: build a Tally XML importer for `Account` (chart of accounts) and opening balances — this is the single highest-leverage feature for migrating Kerala SMBs off Tally.

**Definition of Done:** double-entry validated at the DB level (a Postgres CHECK or app-level validator that rejects unbalanced journal entries), trial balance report reconciles to zero, one client's real chart of accounts imported successfully.

---

## 4. Sprint 2 — Procurement (Weeks 5–7)

**Data model (new `procurement` app):**
```
Vendor(name, gstin, contact, payment_terms, rating)
PurchaseRequisition(requested_by, department, status, items[])
PurchaseOrder(vendor FK, requisition FK nullable, status, expected_date, total)
POLine(po FK, product FK, qty, unit_price)
GoodsReceiptNote(po FK, received_date, received_by)
GRNLine(grn FK, po_line FK, qty_received)
VendorInvoice(po FK, vendor FK, amount, status)
```

**Three-way match logic:** `VendorInvoice` cannot move to `approved` unless `GRNLine.qty_received` matches `POLine.qty` (within tolerance) and `VendorInvoice.amount` matches `PurchaseOrder.total` (within tolerance) — reuse the approval-chain engine being scaffolded in Sprint 0's RBAC layer (extend `Role` with an `approval_limit` field for the PO > ₹50,000 CFO-signoff rule from the strategic plan).

**Event bus hooks:** `po.approved` → notify vendor (email/WhatsApp via Engage bridge, once Sprint 5 lands); `grn.received` → Inventory stock-in event; `vendor_invoice.approved` → Finance journal entry (AP credit).

**Definition of Done:** a full PO → GRN → vendor invoice → payment cycle runs end-to-end and posts correctly to Finance.

---

## 5. Sprint 3 — Warehouse & Order Management (Weeks 6–8, parallel to Sprint 2)

**Data model (new `warehouse` + `orders` apps):**
```
Warehouse(name, address)
Bin(warehouse FK, code)
StockMove(product FK, from_bin, to_bin, qty, reason[receipt/sale/transfer/adjustment], reference)
SalesOrder(customer FK, status, items[], total)
SOLine(order FK, product FK, qty, unit_price, discount)
DeliveryChallan(order FK, dispatched_date, items[])
```

Extends existing `Inventory` module rather than replacing it — `StockMove` becomes the single ledger every other module writes to (Procurement GRN, POS sale, Storefront order, manual adjustment all create `StockMove` rows; current stock = `SUM(StockMove)` per product per warehouse, not a separately-maintained counter — avoids the classic "inventory drift" bug class).

**Key APIs:** `POST /api/orders/sales-orders/`, `.../fulfill/` (creates DeliveryChallan + StockMove out), barcode-scan endpoint for pick/pack confirmation.

**Definition of Done:** an order placed manually (pre-Storefront) flows through fulfillment and correctly decrements stock and creates the corresponding Finance revenue entry.

---

## 6. Sprint 4 — POS (Weeks 8–9)

Thin layer on top of Sprint 1 (Finance) + Sprint 3 (Warehouse/Orders): a POS sale is just a `SalesOrder` with `channel=pos`, immediate fulfillment, and a simplified React checkout screen (offline-tolerant — queue sales locally and sync when connectivity returns, important for Kerala retail floor conditions).

**Definition of Done:** a cashier can complete a sale, print/share a receipt, and see it reflected in Inventory and Finance within the same request cycle.

---

## 7. Sprint 5 — Engage Conversational Channel Abstraction (Weeks 9–10)

**This is the technical core of the Meta/WhatsApp integration** and the highest-leverage sprint in the plan.

**Build inside the existing Engage FastAPI service:**
```
ChannelMessage(channel[whatsapp/instagram/messenger], external_id, direction, contact FK, payload_json, timestamp)
ChannelAdapter (interface): send(contact, template_or_text, media?) -> ChannelMessage
                             receive(webhook_payload) -> ChannelMessage
WhatsAppCloudAdapter(ChannelAdapter)   # first, only, concrete implementation this sprint
```

- Webhook endpoint (`POST /engage/webhooks/whatsapp`) verifies Meta's signature, normalizes the payload into `ChannelMessage`, publishes `channel_message.received` on the event bus.
- Django-side modules (CRM, Support, Order Management) **only ever call** `engage_bridge.send(contact, template, module_context)` — they never touch Meta's API directly. This is what lets Instagram/Messenger be added later as new adapters with zero change to CRM/Order Management code.
- Template message registration: build an internal admin screen to track Meta template approval status (pending/approved/rejected) since templates require Meta review before use.
- WhatsApp Flows: implement the first Flow as the existing Feedback Agent's survey, migrated from free-text to a native Flow form — validates the Flow pipeline before Order Management forms are built on it in Sprint 7.
- Consent: `Contact.whatsapp_opt_in` boolean, captured at CRM lead-creation; adapter refuses to send if false.

**Definition of Done:** a CRM lead created via `POST /api/crm/leads/` triggers a WhatsApp welcome template through the bridge, and an inbound WhatsApp reply updates the same lead record — proving the two-way loop against the shared database.

---

## 8. Sprint 6 — AI Tier 1: Embedded Intelligence (Weeks 10–12)

Ship the two highest-ROI, easiest-to-demo models first:

**CRM lead scoring:**
- Feature set: deal age, contact engagement count (from `ChannelMessage` history — direct payoff from Sprint 5), company size, past deal outcomes.
- Start with a simple logistic regression / gradient-boosted model (scikit-learn), not an LLM — this is a tabular scoring problem, cheaper and more explainable than calling an LLM API per lead.
- Serve via a Django management command (nightly batch score) before building real-time inference — ship the value first, optimize latency later.

**Inventory reorder forecasting:**
- Simple moving-average / exponential-smoothing forecast on `StockMove` history (statsmodels), flags products projected to hit zero before the next expected restock — again, no LLM needed for this class of problem.

**Ask Hertex (Tier 2, start here too since infra overlaps):**
- One endpoint `POST /api/ai/ask/` that takes a natural-language question, uses an LLM (Claude via API) with function-calling to translate intent into a scoped Django ORM query (never raw SQL from the model), executes read-only, and formats the response.
- Critical safety rule: the LLM never writes to the database directly in this phase — read-only queries scoped to the requesting user's tenant/RBAC permissions, enforced in code, not trusted from the model's output.

**Definition of Done:** lead scores visible in the CRM UI and update nightly; a reorder-alert dashboard lists at-risk SKUs; "Ask Hertex" correctly answers 5 predefined test questions against real client data.

---

## 9. Sprint 7 — Storefront, Marketing Automation, Meta Ads (Weeks 12–14)

- **Storefront:** finish the already-designed schema; every order created goes through the same `SalesOrder` model from Sprint 3 (`channel=storefront`) — no separate order table.
- **WhatsApp Commerce:** sync the product catalog (already in `Inventory`) to Meta's Catalog API via a scheduled Celery task; enable in-chat cart through the Sprint 5 adapter.
- **Click-to-WhatsApp Ads:** append a `utm_source`/campaign tag to the WhatsApp deep link used in ads; capture it on first inbound message into `ChannelMessage.payload_json`, propagate to `Lead.source` for attribution.
- **Meta Conversions API:** on `order.completed` event (from Sprint 3's event bus), post a server-side conversion event back to Meta — required once real ad spend needs attribution to Business Suite revenue, not just click data.
- **Marketing Automation module (new `marketing` app):** `Campaign`, `Segment`, `CampaignSend` models; segments are just saved filters over the existing CRM/Order tables (no separate customer-data warehouse needed — again the single-database advantage).

**Definition of Done:** a real Click-to-WhatsApp ad drives a lead into CRM with correct source attribution, and a completed Storefront order fires a Conversions API event Meta's Ads Manager reflects within 24 hours.

---

## 10. Sprint 8 — BI/Analytics, Document Management, Asset Management (Weeks 14–16)

- **BI:** materialized views (Postgres) for the heaviest cross-module reports (revenue by product, sales-cycle length, stock turnover) refreshed nightly via Celery beat; React dashboard consuming them — don't build a separate data warehouse yet, the shared database is small enough for materialized views to suffice at this stage.
- **Document Management:** `Document(model_type, object_id, file, uploaded_by)` generic FK pattern so any module (PO, Invoice, HR contract) can attach documents; integrate a third-party e-signature API (evaluate cost vs. build) rather than building signature capture in-house.
- **Asset Management (new `assets` app):** `Asset(name, category, purchase_date, cost, depreciation_method, current_value)`, monthly Celery task recalculates depreciation and posts a journal entry to Finance.

---

## 11. Sprint 9 — LMS (Weeks 16–18, internal-first)

Simple `Course`, `Lesson`, `Enrollment`, `Progress` models; ship as an internal employee-onboarding tool first (low external risk, real usage data before ever pitching it to clients) — matches the earlier decision to resequence rather than cut this module.

---

## 12. Sprint 10 — No-Code Automation Engine + AI Tier 3 (Weeks 18+, gated on client validation)

**Only start this sprint once 2–3 paying clients are live on Sprints 1–7** (this gate is intentional, not a scheduling nicety — both Engage and HertexFlow were already flagged as needing this validation before further build).

- `WorkflowRule(trigger_event, conditions_json, actions_json, is_active)` consuming the Sprint 0 event bus directly — every event already published (`invoice.posted`, `po.approved`, `channel_message.received`, `order.completed`) becomes a trigger option for free.
- React-based rule builder UI (condition/action blocks, not a full scripting language like Zoho's Deluge — keep it simpler on purpose, per the plan's "don't over-build" principle).
- AI Tier 3 agentic actions become one `action_type` inside this same engine (e.g., "auto-draft WhatsApp follow-up" calls the Sprint 6 Ask-Hertex LLM layer with write permission scoped narrowly to that one action) — this keeps agentic AI inside the same audited, RBAC-governed pipeline as every other automation, rather than a separate uncontrolled agent framework.

---

## 13. Testing & Deployment Notes

- **CI:** run the full Django test suite + one Playwright happy-path per module on every PR; block merges that touch `finance/` or `procurement/` without a passing double-entry/three-way-match test.
- **Staging:** mirror production tenant structure with anonymized data from Aspects Enterprise (or another consenting existing client) — real-shaped data catches integration bugs synthetic fixtures miss.
- **Meta webhook testing:** use Meta's test numbers/sandbox before any production WhatsApp Business Account changes — template rejections and rate limits are the most common source of late-stage surprises.
- **Rollout order per client:** Finance → Inventory/Warehouse/Orders → CRM+Engage/WhatsApp → Storefront/Marketing → BI/Automation. Don't turn on Storefront or Marketing Automation for a client before their Finance/Inventory data is trustworthy — a marketing-driven order against wrong stock data is worse than no automation at all.

---

## 14. What to Build vs. Buy (keep scope honest)

| Component | Build | Buy/Integrate |
|---|---|---|
| Core ERP modules (Finance, Procurement, Inventory, CRM, HR) | ✅ Build — this is the product | |
| WhatsApp/Meta transport | | Meta Cloud API directly (or a BSP like Ozonetel/Wati if you want faster time-to-market on template approval and support) |
| E-signature | | Third-party API (e.g., a DocuSign-class provider) |
| Payments | | Razorpay/PayU |
| SMS/OTP | | Existing SMS gateway provider |
| LLM inference | | Claude API (already your own product's engine) |
| BI dashboard | ✅ Build (React + materialized views) — don't buy a BI tool yet, premature at this scale | |
