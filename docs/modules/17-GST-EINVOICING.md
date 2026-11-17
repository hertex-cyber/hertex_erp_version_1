# 17 — GST & E-Invoicing (Compliance)

**Module owner:** Finance/Compliance
**Rank:** high — this is a legal obligation, and errors block the buyer's Input Tax Credit
**Current state:** only `tax_rate`, `hsn_code`, `gstin` columns scattered across Product/Sales/Customer. **No GST document model, no IRN, no returns, no ITC.**
**Date:** 2026-07-17 · **Reform-aware:** GST 2.0 (22 Sep 2025)

---

## 1. Purpose & scope

Owns India GST compliance end-to-end: tax determination, tax documents (invoices/credit/debit notes with correct fields), e-invoicing (IRN + QR via IRP), e-way bills, GSTR-1/3B/2B + ITC reconciliation, TDS/TCS where applicable, and the audit trail GST demands.

**In scope:** tax engine (rate + place of supply + reverse charge), GST-compliant invoice schema, IRP integration (IRN/QR), e-way bill, GSTR-1/3B/2B, ITC matching, HSN summary, exemption tracking.
**Out of scope (v1):** customs/import GST, SEZ/export complex flows (schema hooks only), composition scheme, TDS/TCS on e-commerce operators, advanced refund workflows.

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `Product.tax_rate`, `Product.hsn_code` | ✅ fields exist |
| `Customer.gstin`, `Vendor.gstin` | ✅ fields exist |
| `Invoice.subtotal/tax/total` | ✅ amounts; tax computed as `base × tax_rate / 100` in POS and Sales (`_price_line`) |
| **Place of supply** | ❌ not modelled — cannot distinguish CGST+SGST (intra-state) from IGST (inter-state) |
| **Tax breakup (CGST/SGST/IGST)** | ❌ only a single `tax` total; **cannot file GSTR-1 which requires the split** |
| **IRN / QR / IRP integration** | ❌ |
| **E-way bill** | ❌ |
| **Credit/debit notes** | ❌ (only "returns" planned in module 05) |
| **GSTR-1 / 3B / 2B** | ❌ |
| **ITC matching** | ❌ |
| **Reverse charge** | ❌ |
| **HSN summary** | ❌ |
| **Tax rate master** | ❌ `tax_rate` is a free decimal on Product — any value accepted |

**Headline (severe):** the current model **cannot produce a GST return**. A document with one `tax` number cannot be split into CGST/SGST vs IGST, which is the primary thing GSTR-1 needs. This is not a refinement gap — it is a compliance block. Every invoice written today would have to be re-derived.

---

## 3. Domain model

### 3.1 The tax rate master (GST 2.0 aware)
**Verified facts as of FY 2026-27:**
- From **22 September 2025** (56th GST Council), the **12% and 28% slabs were abolished.** Primary structure: **0% / 5% / 18%**, plus **40%** for de-merit (luxury/sin) goods.
- Special rates retained: **3%** (gold/jewellery), **1.5%** (cut diamonds), **0.25%** (rough diamonds/stones), **1% / 5%** (real estate without ITC).
- Intra-state = CGST (half) + SGST (half). Inter-state = IGST (full).
- **E-invoicing:** mandatory when **AATO > ₹5 crore** in any FY since 2017-18. Taxpayers **≥ ₹10 crore** must report to the IRP **within 30 days** of the document date (invoices, credit notes and debit notes).
- **E-way bill:** consignment value **> ₹50,000** for goods movement.
- IRP requires **MFA/2FA** on the portal; 6 authorised IRPs.

```
gst_tax_rates
  code, description, rate_pct, effective_from, effective_to, is_active, kind [goods|services]

gst_hsn_master
  hsn_code, description, default_rate_code, uom, is_service (SAC), effective_from
```

### 3.2 Tax documents
```
gst_tax_documents
  doc_type [invoice|credit_note|debit_note|bill_of_supply|delivery_challan],
  doc_number, doc_date, source_type, source_id,
  supplier_gstin, recipient_gstin, recipient_name, place_of_supply_state,
  supply_type [b2b|b2c|export|sez|deemed_export],
  is_reverse_charge, currency, exchange_rate,
  taxable_value, cgst, sgst, igst, cess, total_tax, round_off, total,
  irn, irn_status [pending|generated|failed|cancelled], ack_number, ack_date,
  qr_code, signed_invoice_json, eway_bill_no, eway_valid_until, irp_reported_at

gst_tax_document_lines
  document_id, hsn_code, description, quantity, uom,
  taxable_value, rate_pct, cgst, sgst, igst, cess, discount

gst_einvoice_attempts
  document_id, attempt_no, request_json, response_json, error_code, error_msg, at

NEW:
gst_returns             period, return_type [gstr1|gstr3b|gstr9], status [draft|filed], filed_at, json_ref
gst_itc_ledger          vendor_gstin, invoice_number, invoice_date, taxable_value, igst, cgst, sgst,
                        eligible [yes|no|partial], matched_in_gstr2b (bool), mismatch_reason
gst_reconciliation_runs period, matched, mismatched, missing_in_2b, missing_in_books, created_at
```

### 3.3 Tax determination engine
```
determine_tax(supplier_state, recipient_state, supply_type, lines):
    if supply_type in (export, sez): igst_rate = 0 (or notified)
    inter_state = supplier_state != recipient_state
    for each line: rate = resolve_rate(hsn_code, effective_date)
        if inter_state: igst = taxable * rate
        else: cgst = sgst = taxable * rate / 2
```
Rounding: document-level rounding to match IRP `TotItemVal` validation (BR-08 in module 01).

---

## 4. State machines

### 4.1 Tax document / e-invoice
```
draft       --issue-->      issued        (number assigned, tax determined)
issued      --report-->     reporting     (IRP call in flight)
reporting   --irn-->        irn_generated guard: IRP returned IRN + ack (within 30 days if AATO ≥10Cr)
reporting   --fail-->       irn_failed    guard: retry backlog; error stored
irn_generated --cancel-->   cancelled     guard: within 24h of IRN, reason code → IRP cancel
```
### 4.2 Return
```
draft      --validate-->  validated   guard: all docs for period have IRN where required
validated  --file-->      filed       guard: mismatch resolution signed off
filed      --amend-->     amended
```

---

## 5. API surface

**All new** (no GST endpoints exist today):

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/gst/tax-rates` | CRUD | `finance.tax.manage` | rate master |
| `/gst/hsn` | CRUD | `finance.tax.manage` | HSN/SAC master + search |
| `/gst/documents/{id}/e-invoice` | POST | `finance.tax.manage` | report to IRP → IRN + QR |
| `/gst/documents/{id}/cancel-irn` | POST | `finance.tax.manage` | cancel within window |
| `/gst/documents/{id}/e-way-bill` | POST | `finance.tax.manage` | generate e-way bill |
| `/gst/reports/gstr1/{period}` | GET | `finance.report.read` | GSTR-1 JSON |
| `/gst/reports/gstr3b/{period}` | GET | `finance.report.read` | GSTR-3B |
| `/gst/reports/hsn-summary/{period}` | GET | `finance.report.read` | HSN-wise summary |
| `/gst/itc/import-gstr2b` | POST | `finance.tax.manage` | upload 2B → match |
| `/gst/itc/reconcile/{period}` | POST | `finance.tax.manage` | matching run |
| `/gst/validate-gstin/{gstin}` | GET | `finance.tax.manage` | format + checksum validation |

---

## 6. Business rules

- **GT-01** — Every tax document stores **CGST/SGST/IGST separately**; a single `tax` total is insufficient for returns.
- **GT-02** — Place of supply determines intra vs inter-state; supplier and recipient state come from GSTIN/address, never guessed.
- **GT-03** — Rate is resolved from `gst_tax_rates` at document date (effective-dated), never a free number on the product.
- **GT-04** — E-invoicing applies when AATO > ₹5 Cr (per PAN, any FY since 2017-18); once crossed it never switches off.
- **GT-05** — For AATO ≥ ₹10 Cr, IRN must be generated **within 30 days** of the document date (invoices, credit and debit notes); the IRP rejects beyond that.
- **GT-06** — An invoice with an IRN cannot be edited; correction is a credit/debit note (and IRN cancellation within the 24h window).
- **GT-07** — E-way bill required when consignment value > ₹50,000; Part B transport details may be added later.
- **GT-08** — GSTIN validated by format + state code + checksum before any document uses it.
- **GT-09** — Rounding happens at document level, matching IRP validations (`TotItemVal`).
- **GT-10** — ITC is claimed only against a GSTR-2B match; mismatches go to a reconciliation queue, never auto-claimed.
- **GT-11** — Every IRP call is logged with request/response for audit and dispute.
- **GT-12** — Reverse charge supplies show tax but with no supplier tax collected.

---

## 7. Workflows (end-to-end)

### 7.1 Invoice → IRN → return
1. Sales/Finance issues invoice → tax determined by `determine_tax` (GT-01..03).
2. If e-invoicing applies → `POST /e-invoice` → IRP returns IRN + ack + signed QR (within the 30-day window for ₹10 Cr+).
3. Stored `irn`, `ack_number`, `qr_code`; printed on the invoice PDF (module 19).
4. Period end: generate GSTR-1 JSON from all IRN'd documents; validate; file.
5. GSTR-3B computes liability from the same documents minus ITC.

### 7.2 E-way bill
1. Consignment > ₹50,000 → generate e-way bill from the invoice + transporter + vehicle.
2. Store `eway_bill_no` + validity; link movement to the delivery challan.

### 7.3 ITC reconciliation
1. Download GSTR-2B → import → `gst_itc_ledger`.
2. Match against purchase records (vendor GSTIN + invoice number + date).
3. Mismatches → queue (missing in 2B, missing in books, value mismatch).
4. Only matched ITC is claimed; discrepancy report accompanies the return.

---

## 8. Accounting impact

| Event | Accounting |
|---|---|
| Invoice issued | AR debit / Revenue credit / **GST Output payable (CGST/SGST/IGST separate)** |
| Purchase invoice | Expense/Stock debit / AP credit / **GST Input credit** |
| ITC claimed | GST Input / GST Output set-off |
| Credit note | Reverse revenue + reverse output GST |

Tax must be posted to separate payable/credit accounts per tax head, not a single "tax" account — required for correct GSTR-3B netting.

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally** | GST invoicing, e-way bill, GSTR-1, IRN via GSP | Same-DB with orders/stock; IRP integration native | Tally's GSP network breadth |
| **Zoho Books** | GST returns, e-invoicing, ITC | Native in the ERP not a bolt-on app | Zoho's filing partners |
| **SAP B1 (India)** | GST localization, e-invoicing | Simpler COA + native GST | SAP DRC (Advanced Compliance Reporting) |
| **ClearTax / GST software** | Filing tools | We are the source of truth; filing exports | ClearTax's filing service |

**Differentiator:** GST documents are generated from the same invoice/order/stock data — no re-entry, no reconciliation between billing and compliance.

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **HSN suggestion from product name/description** (taxonomy classifier) | accountant picks the right HSN | suggestion + confidence; accountant confirms |
| 1 | **ITC mismatch risk flag** | accountant chases vendor before filing | read-only |
| 1 | **Anomaly detection** on GST amounts vs historical | catches misclassification | read-only |
| 2 | "What's my GST liability this month?" | instant answer from 3B computation | read-only |

---

## 11. Non-functional & security

- **IRP resilience:** retry with backoff; never lose an un-IRN'd document; a queue for failed attempts with alerting.
- **30-day window:** a daily job flags documents approaching the 30-day reporting limit.
- Performance: GST report generation < 5 s/period.
- RBAC: `finance.tax.manage`, `finance.report.read`.
- Security: IRP credentials (GSP client credentials) encrypted; MFA aware.
- Retention: tax documents 8 years; IRP logs 8 years.

---

## 12. Reporting & analytics

GSTR-1/3B/9, HSN summary, ITC reconciliation, e-invoice success/failure rate, e-way bill register, tax liability trend, tax-head-wise payable balances.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `invoice.posted` | in | create tax document + determine tax |
| `credit_note.issued` | in | create tax document (CN) |
| `grn.received` / `vendor_invoice.approved` | in | input tax entry |
| IRP | → | e-invoice report/cancel |
| E-way bill portal | → | generate/update |
| GST portal | → | GSTR-1/3B filing (export JSON) |

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (tax model)** | tax rate master, HSN master, CBIC/SGST/IGST split, place of supply, GSTIN validation | GT-01..03, GT-08, GT-09 tests; invoice shows correct split |
| **M2 (documents)** | tax-document schema, credit/debit notes wired to returns | GT-06 tests |
| **M3 (e-invoicing)** | IRP integration, IRN/QR, 24h cancel, 30-day window monitoring, attempt log | GT-04/05/11; sandbox IRN generated |
| **M4 (e-way bill)** | generation + validity | GT-07 tests |
| **M5 (returns + ITC)** | GSTR-1/3B generation, 2B import + reconcile, HSN summary | GT-10 tests; return JSON validated against schema |

Order: **M1 (blocks all invoicing) → M2 → M3 → M4 → M5**.

---

## 15. Test plan

- Tax split: intra-state 18% → 9% CGST + 9% SGST; inter-state → 18% IGST (M1).
- Rate effective-dating: a Sep-2025 change applies from the right date (M1).
- GSTIN checksum rejects invalid; accepts valid (M1).
- E-invoice: sandbox IRN returns IRN+QR; fails cleanly on rejected payload (M3).
- Cancel within 24h only (M3).
- GSTR-1 JSON passes schema validation (M5).
- ITC: unmatched invoice not claimed (M5).

---

## 16. Migration & rollout

- Seed `gst_tax_rates` for FY 2026-27 (0/5/18/40 + specials) with `effective_from`.
- Backfill HSN on existing products; tax_rate → rate_code mapping.
- Re-derive historical invoices' tax split where GSTIN/state known (best-effort, flagged).
- Cutover: only documents issued after cutover get IRN; earlier ones are legacy.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Single `tax` total stays | cannot file returns | M1 blocker |
| 12%/28% slabs hardcoded | wrong tax post-reform | effective-dated rate master (GT-03) |
| Missing 30-day IRN window | IRP rejects, invoices invalid | daily flag job |
| ITC auto-claimed unmatched | penalty/interest | GT-10 hard gate |
| GSTIN not validated | rejected invoices | GT-08 |

---

## 18. Definition of Done

- [ ] M1 tax model + split + place of supply + GSTIN validation
- [ ] M2 tax documents + credit/debit notes
- [ ] M3 IRP e-invoicing (sandbox IRN proven) + 30-day monitor
- [ ] M4 e-way bill
- [ ] M5 GSTR-1/3B/2B + ITC reconciliation + HSN summary
- [ ] RBAC, audit, IRP logging, retention
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated