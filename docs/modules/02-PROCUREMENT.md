# 02 — Procurement (Purchase-to-Pay)

**Module owner:** Procurement
**Current state:** models + three-way match + approval exist; GRNI accrual missing, AP posting is inlined and double-counts stock
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns the purchase-to-pay cycle: vendor master, purchase requisitions, purchase orders, goods receipts, vendor invoices, three-way matching, and the AP posting that lands in Finance. Procurement is where the "procure-to-pay" backbone claim (Strategic Plan §1) is actually proven — it is also where the single-database moat is most visible, because Financials and Inventory read the **same** documents.

**In scope:** vendor management, requisition, PO with approval chains (incl. delegated `approval_limit`), GRN, vendor invoice, three-way match, AP posting, GRNI accrual, vendor payment.
**Out of scope (deliberately):** bid/RFQ management (v1), landed cost allocation (v1.5), contract management (module 19-documents), supplier portal/self-service, direct-store-delivery, consignment stock (v2).

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `Vendor`, `PurchaseRequisition`, `PurchaseOrder`, `POLine`, `GoodsReceipt`, `GRNLine`, `VendorInvoice` | ✅ models (`procurement/models.py`, 7 tables) |
| PO creation with lines, status transition | ✅ `router.py` |
| `po.approved` event | ✅ published at `router.py:233` |
| GRN creation → stock-in `StockMove` (movement_type=`receipt`) | ✅ `router.py:237-296`, event `grn.received` |
| **GRNI accrual journal at GRN** | ❌ **missing** — receipt has no accounting entry |
| Three-way match | ✅ `router.py:319-357` — rejects if not fully received (<99%); **5% amount tolerance** |
| `vendor_invoice.approved` → journal | 🟡 `router.py:360-388` — posts **Stock debit / AP credit**; **should be GRNI debit / AP credit** (reverse accrual) |
| Vendor payment | ❌ no endpoint |
| `approval_limit` on Role used | ❌ field exists (`identity/models.py:Role.approval_limit`) but the approve path never reads it |
| Requirement: PO > ₹50,000 needs CFO sign-off | ❌ |
| Tally vendor master import | ❌ (module 18) |

**Headline gaps (verified):** (a) no GRNI accrual → inventory is debited twice (once as `StockMove` at receipt with `unit_cost`, once as journal at invoice approval) and the liability is invisible until the invoice arrives; (b) invoice amount matching is crude — compares invoice total to PO total, not line-by-line unit price & quantity; (c) `approval_limit` exists but is unused.

---

## 3. Domain model

### 3.1 Target entities (extends existing)

```
procurement_vendors
  + add: payment_terms [net_30|cod|advance|...], currency, is_active (soft-delete),
         default_buyer_id, tax_registration (gstin), bank_details (JSON), rating_trend
  → vendor is read by: Finance (AP/credit limit), Inventory (default supplier), Sales (n/a)

procurement_requisitions
  status [draft|pending|approved|rejected]  requested_by  department  required_date
  → add: approval_chain (JSON), budget_note, urgency

procurement_purchase_orders
  status [draft|pending|approved|partially_received|received|cancelled|closed]
  vendor_id  requisition_id  order_date  expected_date
  subtotal  tax  total  notes  approved_by_id  approved_at
  → add: payment_terms, ship_to_warehouse_id, freight, insurance, landed_cost_total,
          currency, tax_summary JSON, incoterms

procurement_po_lines
  product_id  description  quantity  unit_price  received_quantity  line_total
  → add: tax_rate, hsn_code, discount, expected_delivery, line_status

procurement_goods_receipts
  grn_number  purchase_order_id  received_date  received_by_id  notes
  → add: warehouse_id, received_from (carrier), total_qty, status [draft|received|void]

procurement_grn_lines
  grn_id  po_line_id  quantity_received
  → add: unit_cost_received, condition [ok|damaged|shortage]

procurement_vendor_invoices
  invoice_number  vendor_id  purchase_order_id  issue_date  due_date
  amount  tax_amount  status [pending|approved|paid|void]  notes
  → add: currency, payment_reference (when paid), grni_reversed (bool), match_report JSON
```

### 3.2 New tables
```
procurement_vendor_payments   vendor_invoice_id  amount  method  paid_on  reference
procurement_grni_accruals     grn_id  po_id  amount  status [open|reversed]  reversed_by  reversed_at
```

---

## 4. State machines

### 4.1 PurchaseOrder
```
draft            --submit-->       pending
pending          --approve-->      approved    guard: approver has approval_limit >= total, or CFO override   → event po.approved
approved         --receive(part)--> partially_received
approved         --receive(full)--> received     → event grn.received
received         --close-->        closed       guard: all POs received & invoiced, no open GRNI
any non-void     --cancel-->       cancelled    guard: no GRN received yet   → reversal of any partial posting
```
### 4.2 VendorInvoice
```
pending  --match(3way)-->  approved   guard: received >= 99% qty, |total − PO.total| <= 5% tolerance   → AP journal (GRNI reversal)
approved --pay-->         paid       → payment journal, event 'vendor_invoice.paid'
any      --void-->        void       guard: not paid   → reversal JE
```
### 4.3 GRNI accrual
```
open      --reverse-->   reversed   trigger: vendor invoice approved against the GRN
open      --writeoff-->  written_off (aged > policy window, no invoice expected)
```

---

## 5. API surface

Current (`procurement/router.py`): vendors CRUD, requisitions CRUD, POs CRUD + `approve`, `receive`, vendor-invoice approve.

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/procurement/purchase-orders/{id}/submit` | POST | `procurement.purchaseorder.update` | move draft→pending |
| `/procurement/purchase-orders/{id}/approve` | POST | `procurement.po.approve` | approval chain (uses `approval_limit`) |
| `/procurement/purchase-orders/{id}/receive` | POST | `procurement.grn.create` | existing |
| `/procurement/vendor-invoices` | POST | `procurement.vendorinvoice.create` | capture vendor invoice |
| `/procurement/vendor-invoices/{id}/approve` | POST | `procurement.vendorinvoice.update` | 3-way match + AP posting |
| `/procurement/vendor-invoices/{id}/pay` | POST | `procurement.vendorinvoice.update` | record vendor payment → journal |
| `/procurement/grni/aged` | GET | `procurement.vendorinvoice.read` | open GRNI report |
| `/procurement/vendors/import-tally` | POST | `system.tenant.manage` | Tally vendor master (18) |
| `/procurement/reports/vendor-spend` | GET | `analytics.dashboard.read` | spend by vendor/period |

All mutating endpoints: `Idempotency-Key`, audit, outbox.

---

## 6. Business rules

- **PR-01** — A PO cannot be approved by a user whose `approval_limit` < total, unless another approver with sufficient limit signs (delegated approval chain). *(Currently unimplemented.)*
- **PR-02** — PO over ₹50,000 requires a second approver (CFO) unless policy overrides. *(Technical Plan §4; not implemented.)*
- **PR-03** — A PO can only transition to `received`/`partially_received` after at least one GRN exists (guard `<99%` full).
- **PR-04** — Receiving creates both a `StockMove` (Inventory, movement_type=`receipt`) **and** a GRNI accrual journal (Stock debit / GRNI credit). *(Accrual missing — #1 gap.)*
- **PR-05** — Vendor invoice approval requires a three-way match: received qty ≥ 99% of ordered, and unit prices match PO line prices within tolerance — **not** only PO total. *(Currently total-only.)*
- **PR-06** — On approval: reverse the GRNI accrual (GRNI debit / AP credit), never debit Inventory again. *(Currently debits Inventory — double-count.)*
- **PR-07** — AP posting idempotent: `VINV:{invoice_number}` reference; re-approve is a no-op. *(Already true.)*
- **PR-08** — Vendor invoice cannot be voided once paid; payment requires `approved` status.
- **PR-09** — All vendor master GSTINs validated (format); a vendor without GSTIN is flagged for reverse-charge handling.
- **PR-10** — Every procurement event (`po.approved`, `grn.received`, `vendor_invoice.approved`, `vendor_invoice.paid`) goes through the outbox.

---

## 7. Workflows (end-to-end)

### 7.1 Purchase-to-pay (target)
1. User creates requisition → `pending`.
2. Approver approves → PO created `draft` → submit → `pending`.
3. Approval chain: if total > limit, escalate to CFO → `approved`, `po.approved`.
4. Warehouse receives → GRN → `StockMove` (receipt) **+ GRNI accrual** → `grn.received`.
5. Vendor invoice captured → 3-way match → approve → **GRNI reversal + AP** → `vendor_invoice.approved`.
6. Payment → `vendor_payment` → AP debit / Bank credit → `vendor_invoice.paid`.
7. Reports: aged GRNI, aged payables, spend by vendor.

### 7.2 Two-way path (services — no warehouse receipt)
PO → vendor invoice → 2-way match (PO total only) → approve → AP (expense, not stock). v1 supports this with a `receipt_required=False` flag.

---

## 8. Accounting impact (ledger)

| Event | Entry | Status |
|---|---|---|
| GRN received | Stock debit / GRNI credit | ❌ missing |
| Vendor invoice approved | GRNI debit / AP credit | 🟡 wrong (Stock debit / AP credit today) |
| Vendor payment | AP debit / Bank credit | ❌ missing |
| Freight/inspection | Freight expense / AP | optional v1.5 |

**Current double-count proof:** GRN creates `StockMove(quantity=+n, unit_cost)` → Inventory on-hand +n. Approve creates `JournalEntry(Stock debit, AP credit)` → Inventory value +total. Two sources of "stock arrived" = double count, and the balance sheet shows stock value ≠ stock quantity × cost. Fix = GRNI accrual at GRN, reversal at invoice (BR-05/PR-06).

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally** | PO/GRN basic tracking absent in Tally — we beat it by existing | Live 3-way match with GRNI accrual; vendor master from Tally import (18) | Tally's free-form voucher flexibility |
| **Zoho Books/Inventory** | Purchase orders, vendor bills, matching | Deeper: approval_limit chains, GRNI accrual, e-invoice-ready vendor GSTIN | Zoho's procurement-to-pay automation breadth |
| **SAP B1** | PO-GRN-invoice matching, approval workflows | GRNI, landed cost hooks, single-DB visibility | SAP's full RFQ/bid management |
| **Odoo** | Purchase → receipt → vendor bill 3-way match | Cleaner GRNI; approval chains; India GSTIN validation | Odoo community's breadth (reordering, supplier price lists) |
| **NetSuite** | SuiteTax, landed cost | (n/a for v1 Kerala SMB) | consolidation, multi-currency |

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Spend anomaly detection**: vendor price drift vs history, duplicate invoices (same vendor+amount+date window) | AP flags invoice for review before match | read-only; features exposed |
| 1 | **Reorder suggestions** from Inventory forecast → auto-draft PO lines (Tier 1 signal + Tier 3 action) | procurement officer drafts orders in one click | PO still needs human approval (A3) |
| 2 | "Which vendors have open GRNI?", "spend with vendor X this quarter" | quick answers, no report build | read-only, tenant-scoped |
| 3 | **Auto-draft PO** from low-stock forecast (Tier 3, in workflow engine) | approver approves pre-filled PO | approval_limit chain intact; every draft audited |

---

## 11. Non-functional & security

- Concurrency: GRN vs invoice race — lock the PO row (`FOR UPDATE`) during receipt and invoice processing.
- Idempotency: re-approve = no-op (PR-07); re-receive same GRN = error.
- Performance: vendor list < 300 ms at 50k vendors; PO detail < 300 ms.
- Rbac codes: `procurement.vendor.*`, `procurement.requisition.*`, `procurement.purchaseorder.*`, `procurement.goodsreceipt.*`, `procurement.vendorinvoice.*`, plus `procurement.po.approve`, `procurement.grn.create` (already in catalog).
- Field security: vendor bank details visible to finance/purchasing roles only (D4).
- Audit: every PO approval/receipt/invoice approval logged with decision + approver.

---

## 12. Reporting & analytics

KPIs: open POs, GRNI aging, vendor spend, on-time delivery %, PO cycle time, three-way match failure rate (a control metric). Materialised views (module 13): `procurement_po_status`, `procurement_grni_aging`, `procurement_vendor_spend`.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `po.approved` | out | Integrations (vendor WhatsApp/email notice), Finance (commitment view) |
| `grn.received` | out | Inventory (stock-in), Finance (GRNI accrual) |
| `vendor_invoice.approved` | out | Finance (AP), Analytics |
| `vendor_invoice.paid` | out | Finance, Analytics |
| `stock.low` | in | Procurement auto-draft PO (with AI) |

External: Tally export of vendor master (18), vendor notices via Engage (12).

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (accrual fix)** | GRNI accrual at GRN; re-point vendor-invoice AP to GRNI reversal; move journal code into `finance/service.py`; remove Inventory double-debit | Inventory debited once; GRNI ages correctly; no double count (test) |
| **M2 (approval chains)** | `approval_limit` enforcement; ₹50k CFO override; delegated approvers | PR-01/02 tests |
| **M3 (line-level match)** | Replace total-only tolerance with line-by-line qty+price match; match report JSON | PR-05 tests; report shows per-line deltas |
| **M4 (payment)** | vendor payment endpoint + payment journal; paid status; aged payables | Procure-to-pay full cycle posts correctly |
| **M5 (imports + UX)** | Tally vendor/PO import; requisition UI; GRN barcode scan | Migration + demo |

Order: **M1 (must) → M2 → M3 → M4 → M5**.

---

## 15. Test plan

- Invariant: double-count regression (M1) — stock value equals Σ(moves × cost) after full cycle.
- Approval limit: approver below limit rejected; CFO override works; ₹50k rule (M2).
- Match: qty 99% fail; price 6% fail; line-level mismatch report (M3).
- Idempotency: double approve/GRN/invoice.
- Events: outbox carries all four procurement events; subscribers (Finance) receive them.
- Playwright: PO→receive→invoice→pay happy path.
- Failure injection: GRN on cancelled PO; invoice on PO with zero GRN; payment on unapproved invoice.

---

## 16. Migration & rollout

- Tally: import vendors (GSTIN, payment terms), open POs, last 90 days vendor bills → reconcile AP opening balance (module 18).
- Data cutover: freeze legacy POs; import open items; verify GRNI/AP zero reconciliation.
- Feature flags: approval chains, GRNI accrual, line-level match each ship gated.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Double-count ships (M1 skipped) | Finance claims false | M1 release blocker |
| Approval chain bypass | unauthorized spend | enforce in service, test, audit |
| Tally schema drift | import breaks | tolerant parser, per-vendor dry-run |
| GRNI aged items never reversed | overstated liabilities | aged-GRNI report + write-off policy |

---

## 18. Definition of Done

- [x] Migrations (with Alembic baseline)
- [ ] M1 GRNI + AP reversal verified (no double-count test green)
- [ ] M2 approval chains with `approval_limit` + ₹50k rule
- [ ] M3 line-level three-way match with match report
- [ ] M4 vendor payment + full procure-to-pay posting
- [ ] RBAC codes, audit, idempotency, outbox verified
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated