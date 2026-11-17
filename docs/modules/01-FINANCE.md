# 01 — Finance & Accounting

**Module owner:** Finance
**Rank:** highest-risk module (correctness beats speed — Technical Plan §10)
**Status of current code:** partial — double-entry core exists; AP, bank reconciliation, closing and Tally import do not
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns the ledger: chart of accounts, journal entries, invoices (AR), payments, AP, bank reconciliation, period close, financial reporting. It is the module every other module posts into (Invariant I3) — "an ERP whose ledger can be bypassed is a spreadsheet with a UI."

**In scope:** GL, AP/AR, bank reconciliation, cash-flow, reports, period close, GST linkage (via module 17).
**Out of scope (deliberately, per `Best-Product-Plan §3`):** multi-currency consolidation, full SAP-grade cost centres/profit centres in v1, custom financial-statement designer, tax engine beyond GST (this is India-only in v1).

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `Account`, `JournalEntry`, `JournalLine`, `Invoice`, `Payment`, `BankAccount`, `BankTransaction` | ✅ models (`finance/models.py`, 7 tables) |
| Double-entry validation (`_validate_lines`) | ✅ debit==credit, non-zero, no dual-sided line, no negatives |
| Draft→post lifecycle | ✅ but posted entries are not truly immutable (I4 weak) |
| Invoice→AR journal posting | ✅ `post_invoice_journal` — idempotent via `INV:{number}` reference check |
| Trial balance, P&L, balance sheet, cash flow, receivables | ✅ `finance/router.py` `/reports/*` |
| Bank import/reconcile endpoints | ❌ models exist, no import/CSV or match UI |
| **AP (payables)** | 🟡 **partially exists** — `procurement/router.py:361-388` posts debit Inventory / credit AP on vendor-invoice approval. But it is **inlined in Procurement**, not in a Finance service, and it **double-counts inventory** because no GRNI accrual exists at GRN time |
| **Period close / financial close** | ❌ |
| **Tally import** | ❌ (XML envelope verified in module 18 §3; no importer code yet) |
| **Bank feed import** | ❌ |
| **e-invoicing/IRN** | ❌ (module 17) |

**Headline gap (corrected after code re-read):** double-entry *is* real on both sides — AR via `finance/service.py::post_invoice_journal`, AP via `procurement/router.py::approve_vendor_invoice`. What is missing is the **period-correct accounting**: there is no GRNI (goods-received-not-invoiced) accrual at receipt, so stock is debited once at GRN (as a stock move with `unit_cost`) and then debited *again* at invoice approval. Inventory is double-counted and the liability is invisible between receipt and invoice. Payment journals for both AR and AP are also missing. The plan's own test ("a full PO→GRN→invoice→payment cycle posts correctly to Finance") therefore still fails, but at the **payment and accrual** steps rather than at AP.

---

## 3. Domain model

### 3.1 Existing tables → target

```
finance_accounts
  code (String30, idx)  name  account_type [asset|liability|equity|income|expense]
  parent_id (self-FK)   is_system  description
  → add: currency, tax_relevant, report_group, opening_balance, active_balance

finance_journal_entries
  entry_number  entry_date  reference  memo  status [draft|posted|void]
  posted_by_id  posted_at
  → add: version (optimistic lock), reversal_of (FK self, null), outbox_fired

finance_journal_lines
  journal_entry_id  account_id  description  debit  credit
  → add: dimension (cost centre), tax_rate, item_detail (link to sale/PO line)

finance_invoices
  invoice_number  customer_id  issue_date  due_date  status [draft|sent|partially_paid|paid|overdue|void]
  subtotal  tax  total  amount_paid  currency  notes  source_order_id
  → add: gstin_supplier, gstin_buyer, hsn_summary JSON, irn, irn_status,
          qr_code, eway_bill_no, reverse_charge, place_of_supply

finance_payments
  invoice_id  amount  method  paid_on  reference  notes
  → add: bank_account_id, payment_type [receipt|payment|advance|refund],
          linked_journal_entry_id, settlement_reference, is_reconciled

finance_bank_accounts
  name  bank_name  account_number  opening_balance  currency
  → add: bank_code (IFSC), statement_source, statement_format

finance_bank_transactions
  bank_account_id  txn_date  amount  description  reference
  reconciled (bool)  matched_journal_line_id
  → add: unique_hash (to dedupe re-imports), raw_statement_json
```

### 3.2 New tables needed

```
finance_closing_periods   fiscal_year, period_start, period_end, status [open|closing|closed],
                          closed_by, closed_at, reopens_allowed, adjustment_entry_id
finance_tax_records       source [invoice|payment|credit_note], doc_id, gstin, hsn, tax_rate,
                          cgst, sgst, igst, cess, filed (bool), return_id
finance_budget            account_id, period, amount  (v1: thin; enables variance report)
finance_reconcile_rules   name, match_type [amount|reference|date_window], active
```

---

## 4. State machines

### 4.1 JournalEntry
```
draft   --submit-->   draft   (validate balanced)
draft   --post-->     posted    guard: balanced, non-empty, accounts active   → audit, outbox('invoice.posted' if invoice-linked)
posted  --reverse-->  void      guard: not itself a reversal                 → reversal JE, audit, event
posted  --lock-->     posted    (period close marks immutable)
```
I4 requires: no edits to a posted entry; correction = reversal + new entry. Current code does not enforce this — a `PATCH` on a posted entry is possible via the generic CRUD router. **Required fix: override the update path for posted documents.**

### 4.2 Invoice
```
draft          --issue-->     sent
sent           --receive-->   paid      (payment equals balance)   → journal, event 'invoice.paid'
sent           --partial-->   partially_paid
partially_paid --receive-->   paid
sent/partial   --overdue-->   overdue   (date-driven, not user action)
any non-void   --void-->      void      guard: not posted to IRP     → reversal JE, e-invoice cancellation (module 17)
```

### 4.3 Period close
```
open    --start close-->   closing   (begin a closing period; block new postings to prior periods)
closing --adjust-->        closing   (post adjustment entries)
closing --close-->         closed    guard: trial balance == 0, all statements reconciled   → lock prior-period postings
```

---

## 5. API surface

Current router (367 lines) exposes: accounts CRUD, journal CRUD+post, invoice CRUD+post+payment, bank CRUD, reports (trial balance, P&L, balance sheet, cash flow, receivables).

**Add (with permission codes from `permissions_catalog`):**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/finance/journal-entries/{id}/reverse` | POST | `finance.journal.post` | reversal + new entry (I4) |
| `/finance/invoices/{id}/credit-note` | POST | `finance.journal.post` | credit/debit note, GST-linked (17) |
| `/finance/bank-transactions/import` | POST | `finance.banktransaction.create` | CSV/OFX ingest, dedupe by hash |
| `/finance/bank-transactions/reconcile` | POST | `finance.banktransaction.update` | match against journal lines |
| `/finance/periods/close` | POST | `finance.period.close` | period close |
| `/finance/reports/aged-receivables` | GET | `finance.report.read` | AR aging buckets |
| `/finance/reports/aged-payables` | GET | `finance.report.read` | AP aging |
| `/finance/reports/statement/{account_id}` | GET | `finance.report.read` | per-account ledger |
| `/finance/tax-records` | GET/POST | `finance.report.read` | GST recon to GSTR-1/3B |
| `/finance/tally/import` | POST | `system.tenant.manage` | Tally XML → COA + balances (18) |

All mutating endpoints accept `Idempotency-Key` (MA §5.5); all posts validate and write audit; all POSTs use the outbox.

---

## 6. Business rules (numbered, testable)

- **BR-01** — Every journal entry is balanced: `SUM(debit)=SUM(credit)` and `SUM(debit)>0`. Enforced app-level now; target a Postgres trigger.
- **BR-02** — Posted entries are immutable; any change is a reversal + new entry.
- **BR-03** — An invoice cannot be voided if it has an IRN (module 17) unless the IRP cancellation succeeded.
- **BR-04** — A payment cannot exceed `outstanding = total − amount_paid` (already enforced in `create_payment`).
- **BR-05** — Every posted invoice auto-creates AR/Revenue (done); every vendor invoice approval creates AP/Stock (done, but must be **moved into a Finance service** and made GRNI-aware).
- **BR-06** — Bank reconciliation matches a transaction to exactly one journal line; a matched line is removed from the open items.
- **BR-07** — Period close rejects any posting dated before the close date; reports for a closed period are frozen.
- **BR-08** — Rounding is applied at document level, not line level (matches IRP `TotItemVal` validation).
- **BR-09** — All monetary fields are `Numeric(14,2)`; currency stored per document; no implicit INR.
- **BR-10** — Every financial report can be reconstructed from journal entries (no report that reads a "total" column as source of truth).

---

## 7. Workflows (end-to-end)

### 7.1 Order-to-cash (already partially works)
1. `Sales` creates `SalesOrder` → `order.created`.
2. `fulfill_order` → StockMove out + `Invoice(status=sent)` + `post_invoice_journal` (AR debit / Revenue credit) + `DeliveryChallan` + `order.fulfilled`. ✅ verified in code.
3. Payment received → `create_payment` → journal entry (Cash/Bank debit / AR credit) — **not yet implemented** (only the `Payment` row is written).
4. `invoice.paid` → CRM deal close (Tier 1 signal), Analytics.

**Gap: payment journal posting missing.** Add `post_payment_journal(payment)` symmetric to `post_invoice_journal`.

### 7.2 Procure-to-pay (broken at AP — the #1 finance gap)
1. Procurement approves PO → `po.approved`.
2. GRN received → stock-in move + GRNI accrual journal (debit Stock / credit GRNI liability) — **missing**. Without it the receipt has no accounting entry.
3. Vendor invoice approved → reverse GRNI (debit GRNI / credit AP), *not* debit Stock again — current code debits Stock, so stock is counted twice.
4. Payment to vendor → payment journal (debit AP / credit Bank) — missing.
5. Month end: aged payables report reconciles to AP balance in trial balance — must match (BR-10).

### 7.3 Period close (new)
Daily: post all invoices/payments; reconcile bank; generate aged AR/AP. Monthly: trial balance → zero check → adjustments → close → lock period → archive.

---

## 8. Accounting impact (ledger lines created)

| Source | Journal lines | Where |
|---|---|---|
| Invoice issued | AR debit / Revenue credit | `post_invoice_journal` ✅ |
| Payment received | Bank/Cash debit / AR credit | **missing** |
| GRN received | Stock debit / GRNI accrual credit | **missing** |
| Vendor invoice approved | GRNI debit / AP credit (reverse accrual) | 🟡 exists but posts **Stock debit / AP credit** — wrong account, double-counts stock |
| Vendor payment | AP debit / Bank credit | **missing** |
| POS sale | Cash debit / Revenue credit (via Sales order path) | POS module |
| Payroll run | Salary expense debit / AP or Bank credit | HR module |
| Asset depreciation | Depreciation expense debit / Accumulated dep credit | Assets module |
| Stock write-off / adjustment | Inventory loss/gain account | Inventory module |

Every row in this table must exist before the module is "finance-complete". Currently only the first two are.

---

## 9. Benchmarks

| Benchmark | Table stakes we must match | Differentiators (with demo) | Deliberately not competing |
|---|---|---|---|
| **Tally + Excel** | GL, AR/AP, bank, GST returns, print-ready vouchers | One-click Tally import (18); no manual re-entry; live cross-module demo (§2.1) | Tally's depth of vouchers (contra, suspense) — we cover via journal |
| **Zoho Books** | Invoicing, bank feeds, recurring invoices, estimates, tax | AP + AR in one ledger, no sync gaps; single-database reconciliation | Zoho's estimate→invoice→recurring breadth, 45-app ecosystem |
| **SAP Business One** | Approval chains, audit trail, period close, cost centres | Posting engine correctness + India compliance in one DB | SAP's consolidated financials, branch accounting, intercompany |
| **Odoo 18** | Double entry, bank reconc, automated inventory valuation | Simpler India-first COA (GST, Tally parity) | Odoo's community module breadth, analytic accounting |
| **NetSuite** | Multi-subsidiary, reporting | (n/a for Kerala SMB v1) | consolidation, multi-currency |

**Known competitor strengths we will not match in v1:** Zoho's recurring invoice + payment links; SAP's flexible financial statements designer; Odoo's community add-on ecosystem. State these to the team so no one gold-plates them before the §12 fixes land.

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Anomaly detection** on journal entries (amount vs historical, unusual accounts pair, off-hours posting) | flags a human reviewer's queue | read-only; features exposed (A4) |
| 1 | **Cash-flow forecast** (next 30/60/90 days) from AR aging + open POs + recurring | treasury decides whether to chase receivables or draw credit | point forecast with confidence interval |
| 2 | **Ask Hertex**: "outstanding receivables from X", "what's my cash position", "largest overdue invoices" | exec answers a question in seconds | read-only, tenant-scoped (A2) |
| 3 | **Auto-reconcile** bank lines to open journal lines (suggest-and-confirm) | accountant approves a batch, not line-by-line | workflow action type, batch of ≤200, every match audited (A3) |
| 3 | **Auto-draft** follow-up message for overdue invoices via Engage | agent runs the message, human sends | template allow-list, consent gate (A5, A3) |

Tier 1 cash-flow forecast and Tier 3 auto-reconcile are the two that change real work. Start with anomaly detection (cheap, tabular, no LLM).

---

## 11. Non-functional

- **Concurrency:** `SELECT … FOR UPDATE` on journal posting; optimistic `version` on Invoice/JournalEntry; `Idempotency-Key` on all POSTs.
- **Performance:** trial balance < 3 s at 500k lines (index `(tenant_id, journal_entry_id, account_id)`); ledger statement p95 < 500 ms.
- **Volume:** plan for 1M journal lines / year per tenant; monthly archive to `finance_archive_YYYY`.
- **Rounding:** document-level; GST rounding matches IRP rules (module 17).
- **Retention:** 8 years (Companies Act) — archive, never delete.

---

## 12. Security & compliance

- RBAC codes: `finance.account.*`, `finance.journal.*`, `finance.invoice.*`, `finance.payment.*`, `finance.bankaccount.*`, `finance.banktransaction.*`, plus `finance.journal.post`, `finance.report.read` (already in `permissions_catalog`).
- **Add:** `finance.period.close`, `finance.tax.manage`.
- Field-level redaction: bank account numbers, GST credentials visible to finance roles only (D4).
- Audit: every post/reverse/close/payment logged with actor + diff; reversal links to original.
- GST: tax records reconcile to GSTR-1/3B (module 17); DPDP applies to bank/payment data.

---

## 13. Reporting & analytics

Materialised views (Module 13): `finance_trial_balance`, `finance_aged_receivables`, `finance_aged_payables`, `finance_cash_flow_projection`. Reconciliation reports are part of DoD — a finance module without a reconciliation report is unverifiable.

---

## 14. Integrations

| Event | Direction | Target |
|---|---|---|
| `invoice.posted` | out | Procurement (AP mirror), Analytics, Integrations |
| `invoice.paid` | out | CRM (deal close), Analytics |
| `vendor_invoice.approved` | in | **Finance listener → AP journal (missing)** |
| `payroll.processed` | in | Finance → journal (HR) |
| `order.fulfilled` | in | Finance creates invoice (Sales already does it inline — refactor to event) |
| `channel_message.received` | in | Finance — support chat on an invoice → attach |

External: IRP/e-invoicing (17), bank feed import (CSV/OFX), Razorpay/PayU (payments), Tally export/import (18).

---

## 15. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (foundation)** | Postgres double-entry trigger; `version` column; idempotency keys; immutable posted entries; `number_sequences` | All BR-01..BR-10 tests green; no bypass path |
| **M2 (AP + payments)** | GRNI accrual at GRN; re-point vendor invoice to GRNI reversal; AR **and** AP payment journals; relocate AP logic into `finance/service.py` | Procure-to-pay posts correctly end-to-end; inventory debited once (fixes §7.2) |
| **M3 (bank)** | Statement import (CSV/OFX), dedupe hash, reconcile, aged AR/AP | Reconciliation report ties to zero |
| **M4 (close + reports)** | Period close, frozen periods, full report set | Trial balance reconciles; closed period immutable |
| **M5 (Tally import + GST)** | Tally COA/opening balances import; tax records; GSTR-1/3B recon (with 17, 18) | One real client COA imported and reconciled |
| **M6 (AI)** | Anomaly detection; cash-flow forecast; auto-reconcile (Tier 1+3) | Metrics: % auto-matched, forecast error |

Order: **M1 → M2 → M3 → M4 → M5 → M6** (M2 before M3 — you cannot reconcile payables that never post).

---

## 16. Test plan

- Invariant: unbalanced entry rejected (BR-01); posted immutable (BR-02); void requires reversal (BR-03).
- Integration: order→invoice→payment→close produces balanced trial balance; procure-to-pay AP posts (M2).
- Idempotency: double POST of the same `Idempotency-Key` creates one journal (M1).
- Concurrency: two simultaneous posts to the same AR account stay balanced (M1).
- GST: invoice with IRN cannot void without IRP cancellation (M5).
- Playwright happy path: raise invoice, record payment, view statement (M4).
- Failure injection: bank statement re-import dedupes; reversal of a closed-period entry blocked.

---

## 17. Migration & rollout

- **Tally path (18):** COA map → accounts; opening balances → opening JE; last 90 days transactions → journals; reconcile trial balance. Must import unattended in <1 day (`Best-Product-Plan §2.3`).
- **Cutover:** freeze legacy books at month end; import; verify trial balance zero; feature-flag real-time posting.
- **Backfill:** GST records for prior invoices from existing GST data.

---

## 18. Risks & open questions

| Risk | Impact | Mitigation |
|---|---|---|
| AP gap shipping (M2 skipped) | GL cannot represent payables; finance claims collapse | M2 is a release blocker, not a milestone |
| Reversal misuse | audit trail contamination | reversal only via dedicated endpoint; UI has no direct edit on posted |
| Tally XML format drift | migration fails | XML envelope verified (module 18 §3); use a tolerant parser + fixture tests against a real Tally instance |
| Rounding vs IRP | invoice rejected at IRP | document-level rounding (BR-08), golden-master tests |
| Period close race | postings land in closed period | DB-level guard, then app guard |

---

## 19. Definition of Done

- [x] Migrations for all new tables (pending Alembic baseline)
- [ ] All BR-01..BR-10 covered by tests; P&L/BS/trial reconcile to zero
- [ ] M2 AP posting live; procure-to-pay end-to-end test green
- [ ] Bank reconciliation + aged AR/AP reports
- [ ] Period close + frozen periods
- [ ] Tally import (with 18); tax records recon (with 17)
- [ ] OpenAPI + RBAC codes + audit + idempotency all verified
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated

**Owner-type:** senior backend + one CA/accountant for validation.
