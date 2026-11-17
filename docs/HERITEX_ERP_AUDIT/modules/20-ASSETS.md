# 20 — Assets (Fixed Assets, Depreciation, Asset Lifecycle)

**Module owner:** Finance
**Rank:** slice-of-life SMB need — capital goods, vehicles and equipment need a register, depreciation, and disposal accounting; buyers expect it
**Current state:** nothing — no asset model, no depreciation, no register
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns the fixed-asset register: acquisition, capitalisation, depreciation (Companies Act + Income Tax Act schedules), **ITC on capital goods** (GST), revaluation/impairment hooks, disposal/sale/scrap, and the accounting entries that flow from each stage.

**In scope:** asset master, acquisition + capitalisation, depreciation schedules (WDV + SLM, per-Asset and per-AssetClass), ITC on capital assets, partial/fully depreciated states, disposal (sale/scrap/donation) with gains/losses, asset transfer between departments, register reports, audit trail.
**Out of scope (v1):** component/maintenance tracking (asset notes only), project assets (link to module 09), insurance/AMC contracts, real estate land rules beyond basics.

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| Asset model | ❌ none |
| Depreciation engine | ❌ none |
| Asset register | ❌ none |
| Journaling for asset events | ❌ none |

**Headline:** greenfield. Finance (module 01) handles invoices and journals but has no concept of a capital asset. This module adds the register + the deterministic depreciation engine, connected to the same journal service.

---

## 3. Domain model

```
asset_classes
  code, name, depreciation_method [wdv|slm], depreciation_rate_pct,
  it_act_rate_pct (Income Tax Act rate), useful_life_months, residual_pct,
  itc_applicable (bool), itc_reversal_months (proportionate rule), is_default

assets
  id, tenant_id, asset_class_id, name, asset_code (per tenant sequence, module 15),
  acquisition_date, acquisition_cost, vendor_id, po_id, invoice_id,
  status [draft|in_transit|capitalised|partially_depreciated|fully_depreciated|sold|scrapped|written_off],
  capitalised_on, depreciation_start (earlier of: capitalised_on or put-to-use; ITC/165 allows the earliest),
  wdv_method_rate, slm_method_rate, residual_value, useful_life_months,
  location, custodian_department_id, tags_json, notes

asset_depreciation_runs
  period (FY+month), status [pending|running|posted|failed], entries_count, total_amount, posted_at

asset_depreciation_entries
  asset_id, period, method, opening_wdv, depreciation_amount, closing_wdv,
  is_itc_reversal (bool), itc_amount, journal_entry_id (link module 01)

asset_disposals
  asset_id, date, mode [sale|scrap|donation], proceeds, costs,
  sale_invoice_id, gain_loss (computed), journal_entry_id, reason
```

### 3.1 Depreciation methods (binding)
- **SLM (straight line):** `(cost − residual) / useful_life_months` per month; stop at residual.
- **WDV (written down value):** `opening_wdv × rate` per period (annual rate applied on WDV; monthly = `1 − (1 − rate)^(1/12)` or accepted approximation), stop at residual.
- **Companies Act rates** from Schedule II (per asset class; useful life + residual 5%).
- **Income Tax Act rates** (under Section 32) tracked *separately* per asset for the I-T register (block-wise optional) — exposed but not used to post journal entries (journals follow books/Companies Act).
- **ITC on capital goods (GST):** when the asset is later sold/scrapped within **5 years** of capitalisation, input credit is **reversed proportionately** (remaining months/60) — that reversal is journaled to GST input recovery (module 17 interaction).

---

## 4. State machines

### 4.1 Asset lifecycle
```
draft            --purchase-->   in_transit        (PO/GRN/invoice; cost accumulating)
in_transit       --capitalise--> capitalised       guard: invoice posted + available for use; depreciation_start set
capitalised      --depreciate--> partially_depreciated (each run)
partially_dep    --full-->       fully_depreciated  guard: WDV ≤ residual
capitalised      --sell/scrap--> sold/scrapped      guard: disposal posted (gain/loss journaled)
capitalised      --writeoff-->   written_off        guard: impairment, audited
```
### 4.2 Depreciation run
```
queued  --run-->    computing
computing --ok-->   posted     guard: journal entries created; run idempotent (re-run skips posted periods)
computing --fail--> failed     guard: no partial posting; entries rolled back
```

---

## 5. API surface

**All new:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `GET/POST/PUT/DELETE /assets/classes` | CRUD | `finance.asset.manage` | asset class + rates |
| `GET/POST... /assets` | CRUD | `finance.asset.manage` | register operations |
| `POST /assets/{id}/capitalise` | POST | `finance.asset.manage` | capitalise (from invoice/PO) |
| `POST /assets/depreciation/run` | POST | `finance.asset.manage` | run a period |
| `GET /assets/depreciation/register` | GET | `finance.report.read` | full depreciable register |
| `POST /assets/{id}/dispose` | POST | `finance.asset.manage` | sale/scrap with proceeds |
| `POST /assets/{id}/writeoff` | POST | `finance.asset.manage` | impairment write-off |
| `GET /assets/report/register` | GET | `finance.report.read` | register report (opening, additions, dep, closing) |
| `GET /assets/report/itc-monitor` | GET | `finance.report.read` | pending ITC reversal exposure |

---

## 6. Business rules

- **AS-01** — Capitalisation requires a posted invoice (module 01) and put-to-use; cost = invoice + directly attributable costs.
- **AS-02** — Depreciation starts from the **earlier of** capitalisation date and actual use, per GST/IT rules; never before put-to-use.
- **AS-03** — Every depreciation run is idempotent per (asset, period); a re-run never double-posts.
- **AS-04** — Books depreciation (Companies Act) posts the journal; I-T Act rates are a separate register, not journaled.
- **AS-05** — Disposal computes gain/loss = proceeds − (WDV at disposal); journals posted through module 01.
- **AS-06** — ITC proportional reversal (5-year rule) is journaled to GST input recovery on disposal (module 17).
- **AS-07** — WDV never goes below residual value; SLM stops at the residual month.
- **AS-08** — A fully-depreciated, still-in-use asset stays in the register (₹1 / residual value) until disposal.
- **AS-09** — Rate changes need a re-depreciation profile + audit; never silently change historical entries.
- **AS-10** — Asset codes come from module 15 number sequences.

---

## 7. Workflows (end-to-end)

### 7.1 Buy → capitalise → depreciate → sell
1. Purchase invoice approved (module 02/01) → `in_transit`.
2. Put to use → `capitalise` (AS-01/02) → fixed-asset account debited, AP/supplier credited (journal).
3. Monthly run: depreciation posted per asset → accumulated depreciation + P&L dep expense.
4. Sale: disposal → sale proceeds + gain/loss journaled; ITC reversal (AS-06) if within 5 years.

### 7.2 Periodic depreciation close
1. Period close → queue run (beat/Celery).
2. Compute per asset (opening WDV, amount, closing WDV).
3. Post journals atomically; mark period `posted`.
4. Register report regenerated for the period.

---

## 8. Accounting impact (journal map)

| Event | Debit | Credit |
|---|---|---|
| Capitalise | Fixed Asset (by class) | AP / Bank (or Supplier) |
| Depreciation | Depreciation Expense (P&L) | Accumulated Depreciation (BS) |
| Disposal sale | Accumulated Dep + Cash/Bank | Fixed Asset + Gain on Sale (P&L) |
| Scrap/write-off | Accumulated Dep + Loss on disposal | Fixed Asset |
| ITC reversal | GST Input Recoverable (asset) | GST Input Credit (reversal) |

Every entry goes through module 01's journal service (I3/I4 invariants — no orphan entries, balanced, audited).

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally** | Asset register, depreciation (trial) | Engine + register + journaling native | Tally's asset templates |
| **Zoho Books** | Fixed assets, depreciation | IT Act + Companies Act dual registers | Zoho's asset add-on |
| **SAP B1** | Asset master + depreciation (add-on) | SMB-simple, no add-on licensing | SAP's full asset mgmt |
| **Odoo** | Fixed assets + depreciation | GST ITC reversal handling | Odoo's asset breadth |

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Useful-life / rate suggestion** from asset class + description | accountant confirms lifecycle | suggestion + confidence |
| 1 | **ITC reversal reminder** (assets nearing 5-year mark or planned disposal) | when to plan disposals | read-only |
| 2 | "What's my net block this quarter?", "Which assets fully depreciated?" | instant register answers | read-only |

---

## 11. Non-functional & security

- **Determinism:** depreciation is a pure computation; the same (asset, period) always yields the same amounts (AS-03).
- **Idempotency:** run/re-run safe; partial failures roll back.
- Performance: 10k assets × 12 periods < 30 s.
- RBAC: `finance.asset.manage`, `finance.report.read`.
- Audit: capitalise, dispose, write-off, rate change all audited with reason.
- Retention: register + entries 8 years; disposal records 8 years.

---

## 12. Reporting & analytics

Asset register (opening/additions/depreciation/closing per class), GAAP vs I-T depreciation difference, ITC-at-risk monitor, fully-depreciated-but-in-use list, disposal P&L, location/custodian summary.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `purchase.approved` / `invoice.posted` | in | asset creation / in_transit |
| `asset.capitalised`, `asset.depreciation.posted`, `asset.disposed` | out | Finance journal + Analytics |
| `gst.itc.reversal` | out | module 17 / returns |

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (model + classes)** | asset/class tables, register CRUD, asset_code sequences | AS-10 tests |
| **M2 (capitalise + journals)** | capitalise flow, journal linkage | AS-01/02 tests |
| **M3 (depreciation engine)** | SLM + WDV runs, idempotent posting | AS-03/04/07/08 tests, fixture-checked |
| **M4 (disposal + ITC)** | disposal, gain/loss, ITC reversal | AS-05/06 tests |
| **M5 (dual rate + reports)** | I-T Act register, register reports, ITC monitor | AS-04 tests |

Order: **M1 → M2 → M3 → M4 → M5**.

---

## 15. Test plan

- WDV: known fixture (e.g. cost 100k, 15% WDV) → correct periodic WDV (M3).
- SLM stops at residual (M3).
- Re-run a posted period → no double entry (idempotency) (M3).
- Disposal gain/loss correct incl. proceeds < WDV (M4).
- ITC reversal = 1/60th × remaining months on early sale (M4).

---

## 16. Migration & rollout

- Seed asset classes (machinery, vehicles, computers, furniture/office, buildings) with Companies Act + IT Act rates.
- Import existing register (from Tally/Excel) with opening WDV + acquired date; start depreciation from the import month (as-of basis).
- No historical recompute in v1 — go-forward depreciation on imported WDV.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Depreciation start-date wrong | overstated/understated P&L | AS-02 + fixture tests |
| Run double-posted | corrupted ledger | AS-03 idempotency |
| ITC reversal missed | ITC adjustment dispute | AS-06 + M5 monitor |
| Imported register wrong | wrong opening balances | as-of import + owner sign-off |

---

## 18. Definition of Done

- [ ] M1 asset model + classes
- [ ] M2 capitalise + journal linkage
- [ ] M3 SLM/WDV engine (idempotent)
- [ ] M4 disposal + gain/loss + ITC reversal
- [ ] M5 dual registers + reports + ITC monitor
- [ ] RBAC, audit, determinism, retention
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated