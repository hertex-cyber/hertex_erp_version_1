# 01A — Accounting Module Implementation Plan (Complete, Gap-Free ERP Blueprint)

**Module owner:** Finance / ERP Core
**Purpose:** deliver a production-grade accounting layer that is correct, auditable, statutory-compliant, and seamlessly integrated with sales, procurement, inventory, HR, payroll, bank, tax, and external accounting systems.
**Status:** implementation in progress; the first financial-period control slice is delivered.
**Date:** 2026-11-17

---

## 1. Executive summary

This plan closes the missing gaps in the ERP accounting design and converts the current partial finance module into a full accounting backbone aligned with industry-leading practices used by Zoho Books, SAP Financials, and global ERP implementations.

The design is built on the following rules:

- Double-entry is mandatory for every financial transaction.
- Journal entries are append-only and immutable once posted.
- Every business event from sales, procurement, HR, payroll, inventory, and assets must eventually land in the ledger via a validated posting service.
- GL is the source of truth; subledgers are operational views, not separate accounting truth.
- Every accounting variant must reconcile to the ledger, including GST, Tally migration, bank statements, payroll, and fixed assets.
- Every posting must have a traceable source document, user, timestamp, approval context, and reversal path.

This plan includes backend implementation, frontend UX, data model, workflows, external system integrations, controls, reports, and rollout phases. It covers the accounting module for a multi-entity, multi-branch, multi-currency, GST-compliant ERP used in an Indian SMB/SME environment with potential global expansion.

---

## 2. Accounting module objective in the ERP

The accounting module is not a reporting layer; it is the financial control plane of the ERP.

It must support:

- Chart of accounts and account groups
- Ledgers and subledgers
- Journal entries and reversals
- AR and AP accounting
- Bank and cash accounting
- GST, TDS, PF, ESI, and tax reconciliation
- Inventory valuation and GRNI accruals
- Fixed asset accounting and depreciation
- Payroll accounting
- Consolidation and multi-entity reporting
- Period close and locking
- Audit trail, approval controls, and segregation of duties
- Integration with banks, payment gateways, tax portals, and external ERPs

---

## 3. What global best practice requires

### 3.1 Zoho Books pattern

Zoho Books emphasizes:

- simple accounting workflows,
- connected bank feeds,
- recurring invoice automation,
- mobile-first financial activities,
- GST compliance workflows,
- role-based collaboration,
- integrations with payments, inventory, and payroll.

Best practice takeaway:

- The accounting UX should be simple, fast, and role-specific.
- Banking and reconciliation should be automated and familiar to accountants.
- Tax filing and document generation should be tightly integrated.

### 3.2 SAP Financials pattern

SAP financial architecture prioritizes:

- stable GL engine,
- strong year/period close controls,
- posting rules and validation,
- cost center and profitability dimensioning,
- auditability,
- enterprise-level consolidation and reporting.

Best practice takeaway:

- Period-close logic must be explicit and enforceable.
- Approval and locking rules must be institutional, not optional.
- Dimensions like branch, cost center, department, project, and tax code must be structurally supported.

### 3.3 Worldwide ERP accounting pattern

Across mature ERP systems, the strongest accounting implementations share these principles:

- Immutable ledger: no direct edits to historical posted entries.
- Revenue recognition by source document and policy, not by ad hoc spreadsheet logic.
- Zero tolerance for unposted operational events in the final books.
- Reconciliation at every boundary: bank, GST, payroll, inventory, AP, AR.
- Auditability: every journal, reversal, and user action has an identity and timestamp.
- Bridging from operational modules to accounting via domain events and posting service APIs.

---

## 4. Critical gaps in current Hertex design and how to close them

The current project already identifies a number of finance issues. The accounting plan below resolves them completely.

### Gap 1: GRNI accrual is missing

Problem:

- Goods received are not encoded in the general ledger as a payable accrual before invoice receipt.
- This causes inventory and liability mismatches.

Fix:

- Add GRNI accrual on Goods Receipt (GRN).
- Journal: Debit Inventory / Stock Control; Credit Goods Received Not Invoiced (GRNI) liability.
- On vendor invoice approval: reverse that accrual and post AP.

### Gap 2: AP posting ownership and event delivery

Status: Goods receipts now create a linked, posted inventory-to-GRNI journal within the receipt transaction. Invoice approval clears the complete set of receipt accruals for its PO and posts GRNI to AP through Finance. Receipts predating this flow are blocked from invoice approval pending reconciliation rather than silently skipped. Procurement still invokes finance posting synchronously; durable source-event delivery and retry handling remain part of the idempotency/outbox work.

Remaining accounting detail: the current baseline uses inventory for invoice-to-receipt value differences and tax while tax account/category mapping remains undefined. The current three-way match assumes one approved vendor invoice clears all receipts for a PO; split billing needs explicit receipt-to-invoice allocation before it is supported.

### Gap 3: Payment journals are missing

Problem:

- Invoices are posted to AR, but payment settlement does not create the expected cash/bank and AR clearing journal.

Fix:

- Add payment posting logic for both AR receipt and AP payment.
- Support cash, bank, cheque, UPI, NEFT/RTGS, card, and settlement gateway methods.

### Gap 4: No close-period control

Problem:

- There is no locking mechanism to prevent accidental changes in a closed period.

Fix:

- Add financial period object and close workflow.
- Freeze postings to prior periods unless an authorized adjustment is created.

### Gap 5: No bank matching and statement import policy

Status: A first controlled CSV reconciliation workflow is implemented. It imports normalized CSV rows with per-account duplicate hashes, suggests same-signed-amount matches to posted GL lines on the mapped bank account within a 14-day window, supports explicit matching/unmatching and a separate reconcile action, audits changes, and keeps unmatched lines in an exception queue. Direct generic CRUD no longer permits setting a transaction reconciled without a match.

Remaining: bank feeds and OFX formats, configurable matching rules/date tolerance, statement-level opening/closing balances and period-based sign-off are not implemented. Current difference compares the imported transaction movement with the linked posted journal lines, so it measures the unmatched exception balance rather than a statement closing-balance reconciliation.

### Gap 6: No tax reconciliation and compliance engine at the accounting layer

Problem:

- GST logic exists as a module, but accounting must validate every tax posting consistently.

Fix:

- Store tax records at the journal line and invoice level.
- Reconcile GST returns against actual sales and purchase entries.
- Support IRN/e-invoice, GSTR-1/3B, and ITC reconciliation.

### Gap 7: Payroll and asset journals are not integrated into the ledger

Problem:

- Payroll and fixed assets are missing from accounting flow.

Fix:

- Salary journal: Debit salary expense, credit employee payable, PF/ESI/TDS payable, and cash/bank as needed.
- Depreciation and disposal: create asset-specific journals along the accounting policy.

---

## 5. Target accounting architecture

### 5.1 Core accounting layers

1. Operational layer
   - Sales, procurement, HR, payroll, inventory, warehouse, POS, payments, assets.

2. Event and domain layer
   - Domain events such as `invoice.posted`, `payment.captured`, `grn.received`, `payroll.processed`, `asset.capitalised`.

3. Posting service layer
   - The canonical accounting engine that transforms domain events into journal entries.

4. Ledger layer
   - Journal headers, lines, accounts, balances, period state, and audit trail.

5. Reporting layer
   - Trial balance, P&L, balance sheet, cash flow, aging, tax, board dashboards, and export reports.

6. Compliance and audit layer
   - Approvals, user actions, control checks, reversals, regulatory filings, and external integration logs.

---

## 6. Proposed backend domain model

### 6.1 Ledger core

```sql
finance_accounts
- id
- tenant_id
- code
- name
- account_type  -- asset, liability, equity, income, expense
- parent_account_id
- status
- currency
- is_system
- tax_relevant
- active
- opening_balance
- created_at
- updated_at

finance_journal_entries
- id
- tenant_id
- entry_number
- entry_date
- reference
- source_module
- source_document_type
- source_document_id
- memo
- status -- draft, posted, reversed, void
- posted_by
- posted_at
- reversal_of_entry_id
- period_id
- idempotency_key
- created_at

finance_journal_lines
- id
- journal_entry_id
- account_id
- line_type -- debit, credit
- amount
- currency
- description
- tax_rate
- project_id
- cost_center_id
- branch_id
- department_id
- reference
- created_at

finance_ledger_balances
- account_id
- period_id
- opening_balance
- debit_total
- credit_total
- closing_balance
- updated_at
```

### 6.2 Receivables, payables, and cash

```sql
finance_customers
- id
- tenant_id
- customer_code
- name
- gstin
- credit_limit
- status

finance_vendors
- id
- tenant_id
- vendor_code
- name
- gstin
- credit_term_days
- status

finance_invoices
- id
- tenant_id
- invoice_number
- customer_id
- issue_date
- due_date
- status
- subtotal
- tax_total
- total_amount
- paid_amount
- currency
- source_module
- source_document_id
- linked_order_id
- created_at

finance_payments
- id
- tenant_id
- payment_number
- payment_type -- receipt, payment, refund, adjustment
- invoice_id
- customer_id
- vendor_id
- bank_account_id
- payment_method
- amount
- payment_date
- reference
- status -- pending, posted, reconciled, failed
- created_at

finance_bank_accounts
- id
- tenant_id
- name
- bank_name
- account_number_masked
- ifsc_code
- account_type
- currency
- status

finance_bank_transactions
- id
- bank_account_id
- statement_date
- external_reference
- description
- amount
- direction
- status
- matched_journal_line_id
- hash_key
- raw_payload
```

### 6.3 Tax, period, and controls

```sql
finance_periods
- id
- tenant_id
- fiscal_year
- period_name
- start_date
- end_date
- status
- closed_by
- closed_at

finance_tax_records
- id
- tenant_id
- tax_type -- GST, TDS, PF, ESI
- source_document_type
- source_document_id
- tax_code
- taxable_amount
- tax_amount
- input_output_type
- gstin
- filing_period
- status

finance_approval_workflows
- id
- tenant_id
- entity_type
- entity_id
- approval_type
- current_step
- status
- initiated_by
- approved_by
- approved_at

finance_audit_log
- id
- tenant_id
- entity_type
- entity_id
- action
- actor_user_id
- actor_role
- old_value
- new_value
- created_at
```

---

## 7. Posting model: mandatory accounting rules

Every operational event must be posted by a single canonical accounting rule.

### 7.1 Sales invoice posting

Trigger: `invoice.posted`

Journal:

- Debit Accounts Receivable
- Credit Revenue
- Credit/ Debit tax payable based on tax code

### 7.2 Payment receipt posting

Trigger: `payment.received`

Journal:

- Debit Bank/Cash
- Credit Accounts Receivable

### 7.3 Purchase receipt posting (GRN / accrual)

Trigger: `grn.received`

Journal:

- Debit Stock / Inventory Control
- Credit Goods Received Not Invoiced (GRNI) Liability

### 7.4 Vendor invoice posting

Trigger: `vendor_invoice.approved`

Journal:

- Debit GRNI / Accrual Clearing
- Credit Accounts Payable
- Tax payable or input tax credit adjustments as relevant

### 7.5 Vendor payment posting

Trigger: `vendor_payment.posted`

Journal:

- Debit Accounts Payable
- Credit Bank/Cash

### 7.6 Payroll posting

Trigger: `payroll.processed`

Journal:

- Debit Salary Expense
- Credit Employee Payables / PF / ESI / TDS / Bank

### 7.7 Asset accounting

Trigger: `asset.capitalised`, `asset.depreciation.created`, `asset.disposed`

Journal:

- Asset purchase: Debit Fixed Asset, Credit AP/Bank
- Depreciation: Debit Depreciation Expense, Credit Accumulated Depreciation
- Disposal: remove carrying value, post gain/loss

---

## 8. Frontend accounting module design

The frontend must support both operational accounting and leadership decision-making.

### 8.1 Required accounting screens

1. Dashboard
   - cash position
   - receivables outstanding
   - payables aging
   - cash flow trend
   - expense by category
   - GST and tax exposure

2. Chart of Accounts
   - account tree
   - account code validation
   - active/inactive account state
   - account locking policy

3. Journal Entry screen
   - line-level debit/credit editing
   - validation before posting
   - reversal and void actions
   - audit panel

4. Invoice and payments screen
   - invoice issue, due dates, aged receivables
   - payment allocation
   - credit notes and adjustments

5. Vendor bills and AP workbench
   - approvals and matching
   - GRNI accrual visibility
   - 3-way match with PO/GRN

6. Bank reconciliation screen
   - imported bank statements
   - auto-match suggestions
   - manual match and exception queue

7. Period close screen
   - close checklist
   - account balances
   - unposted transaction warning
   - closure approval log

8. Tax and GST screen
   - GST summary
   - GSTR data
   - ITC reconciliation
   - e-invoice status tracking

9. Payroll and HR cost screen
   - monthly payroll cost summary
   - statutory liabilities
   - posting status

10. Fixed asset register
    - asset additions, depreciation, disposal, impairment, write-offs

### 8.2 Frontend best practices

- Use role-based financial dashboards; accountants, CFO, and operations see different information.
- Every financial screen should include a unified audit timeline.
- For audit-critical actions, require approval and reason code.
- Use server-validated financial actions; the frontend alone is never the authority.
- Emphasize read-only reporting with strong filtering and export features.

---

## 9. Backend service design

### 9.1 Main financial services

- `account_service`
- `journal_service`
- `posting_service`
- `reconciliation_service`
- `tax_service`
- `period_close_service`
- `reporting_service`
- `payment_service`
- `bank_feed_service`
- `asset_accounting_service`

### 9.2 Service responsibilities

`posting_service` is the heart of the module. It must own:

- posting rules,
- validation,
- idempotency,
- reversal logic,
- posting events,
- ledger balance updates,
- audit integration,
- outbox event publication.

### 9.3 Security and control patterns

- Every mutating accounting action must be user-scoped and role-scoped.
- Any posted financial document should require an `approval_context` or `audit_context` payload.
- No direct editing of historical journals.
- A posting cannot happen when the target period is closed.
- Freeze logically before the business closes books for month or year.

---

## 10. Integrations and system connections

### 10.1 Core ERP internal integrations

- Sales → accounting: invoice and payment postings
- Procurement → accounting: GRN accrual and AP posting
- Inventory → accounting: stock write-offs, stock losses, valuation adjustments
- HR / payroll → accounting: salary, PF, ESI, TDS journals
- Projects → accounting: time and milestone billing
- Assets → accounting: asset additions, depreciation, disposal
- Analytics → accounting: board reporting, risk monitoring, variance analysis

### 10.2 External system integrations

- Banks: bank statement import and direct feed integration
- Payment gateways: Razorpay, PayU, PhonePe, UPI, NEFT/RTGS
- GST portals: e-invoice, e-way bill, GSTR filing, returns
- Tally: migration import/export and trial-balance reconciliation
- Zoho Books: data pipeline mapping and comparison for finance parity
- SAP: GL export/import, enterprise financial statement mapping, multi-entity consolidation
- OCR / document processing: vendor invoice ingestion, document extraction
- Email / WhatsApp / ERP messaging for invoice alerts and payment follow-ups

### 10.3 Integration patterns

Use:

- outbox pattern,
- webhook delivery,
- idempotent import handlers,
- signature verification,
- retry with dead-letter queues,
- per-tenant data isolation,
- gateway and financial institution reconciliation logs.

---

## 11. Industry best-practice controls for accounting

### 11.1 Finance controls

- Segregation of duties between invoice creation, approval, and payment release.
- Dual approval for large payments or manual journal entries.
- Delegation matrix for financial close.
- Exception queue for bank and tax mismatches.
- Automated compliance checks on journal value and document classification.

### 11.2 Audit controls

- Full before/after change log for each accounting object.
- Immutable journal history.
- Action trace with user, role, tenant, IP, and timestamp.
- Reversal journal required for every correction.

### 11.3 Risk controls

- account-code drift prevention
- duplicate invoice detection
- duplicate payment prevention
- over-credit limit checks
- blocked posting during close period
- no posting to inactive accounts

---

## 12. Reporting and analytics requirements

The accounting module must generate:

- Trial balance
- General ledger
- Balance sheet
- Profit and loss statement
- Cash flow statement
- Aging reports (AR/AP)
- Budget vs actual
- Cost centre reports
- GST summary and return reports
- Bank reconciliation report
- Payroll cost report
- Fixed asset register and depreciation report
- Intercompany and branch reports

All reports must be generated from the ledger and journal entries, never from manually maintained totals.

---

## 13. Implementation roadmap

**Progress as of 2026-11-18:** Phase 0 has started. Financial periods can be created, listed, closed, and reopened with audit events. Period ranges cannot overlap, closure is blocked while draft journals remain, and journal, sales-invoice, vendor-invoice, payment, GRN, payroll, and Tally opening-balance postings are checked against the configured open period. Journal lines are validated for balance, valid debit/credit sides, supported precision, and active same-tenant accounts. If a tenant has not configured any periods yet, existing posting behavior remains available for rollout compatibility; after the first period is configured, postings require a matching open period. Posted journals can be corrected with a reasoned, permission-controlled, linked reversal; the original remains unchanged, reversal requests are idempotent, and a database constraint prevents multiple reversals of one journal. Chart-of-accounts codes are normalized and unique per tenant, parent references are tenant/type checked and cycle-safe, and accounts with posted history cannot be reclassified or deactivated. GRNs now debit inventory and credit a seeded GRNI liability account, with a unique linked accrual record; vendor invoice approval clears those accruals and credits AP. Inventory count adjustments now create append-only, idempotent stock movements and balanced, linked journals atomically; positive adjustments debit inventory and credit the adjustment expense account, while write-offs reverse those lines. The current standard mappings use account codes 1200 (inventory) and 5000 (inventory adjustment expense/COGS), so tenants must map those codes in their chart before posting. Payroll processing now accrues gross salaries to expense and credits net wages plus employee PF, ESI, and TDS withholdings to separate payable accounts; the period-end journal is linked to the payroll run, and duplicate period runs are blocked. Existing payroll deduction formulas are still provisional estimates and are not statutory-ready: employer contributions, tax slabs, exemptions, state-specific rules, payment/remittance, and statutory reporting must be implemented and reviewed before production payroll use. Receipts without their expected accrual are explicitly blocked for reconciliation. Customer receipts require an idempotency key, a posted invoice, and a cash or mapped bank GL account; payment, invoice balance, and posted journal commit together. Vendor disbursements use the same transactional/idempotent pattern: approved posted bills track paid/outstanding balances and each settlement debits AP, credits the configured cash/bank asset, and links to its journal. A dedicated Finance overview and AP workbench provide task-focused screens; chart, period, and bank setup registers remain table-oriented. Bank reconciliation now supports deduplicated CSV imports, exact auto-match suggestions, audited manual match/reconcile actions, and an unmatched exception queue; external feeds/OFX and statement-level closing balance sign-off remain open. The GST accounting foundation now supports tenant-scoped registrations (with an automatic first default), validated Indian state codes, tax codes with liability/ITC account mappings, line-level classification and immutable tax/eligibility snapshots, and intra/inter-state CGST/SGST/IGST calculation. Sales orders, POS checkout, customer invoices, and vendor invoices carry GST snapshots into ledger posting; classification is mandatory for posting once GST is enabled. Sales-order fulfillment and POS checkout are covered by regression tests for default registration, tax classification enforcement, and intra/inter-state tax posting. The GST return/filer, e-invoicing/e-way bill, reconciliation to portal data, and broader tax scope remain open. Pre-existing customer payments without journal links are retained and surfaced for ledger review rather than silently backfilled. Remaining roadmap work includes production-ready payroll rules and remittance, durable source-event idempotency, bank-feed/OFX integration, statement-level sign-off, account groups, and GST statutory workflows.

The initial maker-checker matrix is implemented for manual journals, vendor disbursements, and inventory adjustments. Requests are tenant-scoped, audited, and decided by a different user with distinct read/approve/reject permissions and a required reason. Vendor-payment requests reserve available invoice balance; pending/rejected adjustments do not change stock-on-hand, and pending requests do not create ledger postings. Approval revalidates the open period, invoice balance, bank mapping, and inventory ledger accounts in the same transaction as posting. Customer receipts and automated operational journals remain unchanged; amount thresholds, configurable policy administration, and second-level/dual approval are later controls.

### Phase 0 — Foundation and controls

- [ ] finalize chart of accounts structure
- [ ] create account groups and ledger rules
- [x] enforce unique normalized account codes and safe account hierarchy
- [x] define financial periods and close/reopen workflow, with posting-date enforcement
- [x] add foundational journal-line validation and tenant account checks
- [ ] complete source-event idempotency and audit-log model
- [x] add period permissions and role mapping

### Phase 1 — Core accounting engine

- [x] GL posting and journal reversal
- [x] AR invoice posting
- [x] baseline AP vendor invoice posting through finance service
- [x] customer payment posting and cash/bank settlement
- [x] vendor payment disbursement and settlement with idempotent journal posting
- [x] basic trial balance and P&L from posted journals

### Phase 2 — Operational integration closure

- [x] GRN inventory / GRNI accrual and vendor invoice clearing
- [x] baseline bank reconciliation: CSV import, deduplication, suggestions, manual match, exception queue, and confirmation
- [x] GST registration, line-level classification, calculation, account mapping, and posting foundation
- [x] verify sales-order fulfillment and POS GST posting with regression tests
- [x] inventory adjustment posting with linked, idempotent journals
- [x] payroll journal posting with period-end accruals and payable account breakdown

### Phase 3 — Controls and close

- [x] year/period close and reopen logic
- [x] maker-checker approval matrix for manual journals, vendor disbursements, and inventory adjustments
- [x] aging analytics and exception monitoring
- [x] close checklist and signed-off close process

### Phase 4 — Tax, assets, and external sync

- GST filing/returns, portal reconciliation, and statutory export support
- e-invoice and e-way bill integration
- asset register and depreciation engine
- Tally migration and reconciliation
- bank feed connectors

### Phase 5 — Enterprise and consolidation

- multi-entity and intercompany accounting
- branch and cost-center reporting
- consolidation views
- advanced dashboarding and KPI monitoring

---

## 14. Acceptance criteria

The accounting module is considered complete only if all of the following are demonstrably true:

- every operational event creates a correct journal entry
- every payment, AP, and AR action is posted and reconciled
- GRN accrual, AP reversal, and payment settlement are all supported
- period close blocks further edits to closed periods
- all reports reconcile to the ledger
- every financial action leaves an audit trail
- GST and tax reports tie to journal postings
- bank statements match actual ledger transactions
- asset and payroll journals are generated automatically and correctly
- no module bypasses the accounting service

---

## 15. Missing-gap closure checklist

| Area | Status before | Final status after plan |
|---|---|---|
| Chart of accounts | Partial | Hierarchy controls implemented; account groups and final COA design remain |
| Journal validation | Partial | Complete |
| AR posting | Present | Hardened |
| AP posting | In procurement | Moved to finance service |
| GRNI accrual | Missing | Implemented |
| Journal immutability | Weak | Enforced |
| Payment journals | Missing | Added |
| Period close | Missing | Added |
| Bank reconciliation | Missing | CSV workflow implemented; feeds and statement sign-off remain |
| GST reconciliation | Partial | Posting foundation implemented; statutory filing and portal reconciliation remain |
| Payroll accounting | Missing | Planned; payroll journal posting remains open |
| Fixed asset accounting | Missing | Planned; asset register and depreciation remain open |
| Ledger reporting | Partial | Complete |
| Multi-entity controls | Planned | Planned; not yet implemented |
| Audit log | Partial | Complete |

---

## 16. Recommended project execution pattern

### Back-end workstreams

1. Ledger schema and posting engine
2. AR/AP and payment modules
3. Period close and audit controls
4. Tax and GST engine
5. Bank reconciliation and statement imports
6. Payroll and asset accounting integration
7. Reports and dashboards

### Front-end workstreams

1. Finance dashboard
2. GL and accounts tree
3. Journal and invoice screens
4. AP/AR workbench
5. Bank reconciliation UI
6. GST and tax screen
7. Period close and audit UI
8. CFO and board dashboards

---

## 17. Final recommendation

The Hertex ERP should not treat accounting as an "optional feature" or a thin reporting add-on. It must be the transactional control layer that every operational module feeds into.

The winning ERP accounting design is not the one with the most forms; it is the one with the strongest ledger logic, the clearest approval controls, the most accurate reconciliation, and the cleanest path to tax compliance and financial close.

This plan provides the operational blueprint to achieve that standard.

---

## 18. Sources and design references used

- Current internal ERP document set in `docs/modules/01-FINANCE.md`, `02-PROCUREMENT.md`, `08-HR.md`, `17-GST-EINVOICING.md`, `20-ASSETS.md`.
- Zoho Books product positioning and accounting workflows.
- SAP finance architecture principles and enterprise financial control expectations.
- Standard ERP accounting best practice across global implementations: double-entry, immutable ledger, period close, audit trail, subledger reconciliation, and tax integration.
