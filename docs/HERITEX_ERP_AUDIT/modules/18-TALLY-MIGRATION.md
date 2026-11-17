# 18 — Tally Migration & Integration

**Module owner:** Integrations
**Rank:** the plan's top moat — **95% of target SMBs run Tally**; the migration is the on-ramp and the coexistence bridge is the retention hook
**Current state:** no Tally code at all; migration is `UNVERIFIED` territory, now grounded with official Tally docs
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns everything Tally: (a) **one-time migration** of chart of accounts, masters, stock, and opening balances from Tally into Hertex, and (b) **ongoing coexistence** — pushing Hertex vouchers back into Tally (many accountants keep Tally as their official books for years).

**In scope:** Tally XML export/import (HTTP/XML + ODBC read), chart-of-accounts mapping, master sync, voucher (journal/sales/purchase/payment) export to Tally, reconciliation of balances, import/export logs.
**Out of scope (v1):** TDL custom reports, payroll migration from Tally's payroll add-on, multi-branch/consolidation edge cases, real-time two-way sync (batch push + pull is enough).

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| Tally integration | ❌ **nothing in the codebase** (no router, no service, no models) |
| Migration utilities | ❌ none |
| Notes in other modules | 🟡 modules 01/02/05/17 all *mention* Tally as a dependency ("balances must reconcile with Tally") but nothing implements it |

**Headline:** Tally is referenced as a constraint everywhere but implemented nowhere. This module is greenfield; the good news is the integration surface is **standard and well-documented** (below).

---

## 3. Verified Tally integration surface

From **official Tally developer docs** (TallyHelp "Sample XML", "Integration Initiated From TPAs", Tally.ERP 9 Integration Capabilities) — verified 2026-07-17:

### 3.1 Tally as a server (TPA pulls or pushes)
- Tally runs in **server mode with HTTP listener** (default port **9000**).
- Collections exposed: **Ledger, Voucher, StockItem, CostCentre**, etc. (ODBC marks `IsODBCTable: Yes`; HTTP/XML via `Export Data` request).
- **ODBC = read-only**; **XML = read + write**.

### 3.2 XML envelope (the message format)
```
<ENVELOPE>
  <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>   (or Export)
  <BODY><IMPORTDATA>
    <REQUESTDESC>
      <REPORTNAME>Vouchers</REPORTNAME>                        (or Ledgers, Masters, etc.)
      <STATICVARIABLES><SVCURRENTCOMPANY>Acme Traders</SVCURRENTCOMPANY></STATICVARIABLES>
    </REQUESTDESC>
    <REQUESTDATA>
      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <VOUCHER VCHTYPE="Payment" ACTION="Create">
          <DATE>20260315</DATE>
          <VOUCHERTYPENAME>Payment</VOUCHERTYPENAME>
          <NARRATION>...</NARRATION>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>Suspense A/c</LEDGERNAME>
            <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>   debit side
            <AMOUNT>-4520.00</AMOUNT>                  debit is negative
          </ALLLEDGERENTRIES.LIST>
          <ALLLEDGERENTRIES.LIST>
            <LEDGERNAME>HDFC Bank A/c</LEDGERNAME>
            <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>    credit side
            <AMOUNT>4520.00</AMOUNT>                   credit is positive
          </ALLLEDGERENTRIES.LIST>
        </VOUCHER>
      </TALLYMESSAGE>
    </REQUESTDATA>
  </IMPORTDATA></BODY>
</ENVELOPE>
```
**Key facts:**
- Mandatory tags: `TALLYREQUEST`, `REPORTNAME`, `TALLYMESSAGE`, `VOUCHER` (+ context fields).
- **Sign convention is inverted**: debit = `ISDEEMEDPOSITIVE: Yes` with **negative** `AMOUNT`; credit = `No` with positive amount.
- **Vouchers must sum to zero** or Tally rejects them — our converter must write both legs, balanced.
- Response: `CREATED=1`, `ERRORS=0` on success; errors counted in the response.
- Ledgers must be created under a **Group** (`PARENT` tag), and groups before ledgers; masters before vouchers.
- Alternate header form: `TALLYREQUEST=Import`, `TYPE=Data`, `ID=Vouchers` — both work.

### 3.3 Verification anchors
- [x] TallyHelp Sample XML (ledger/group creation, `PARENT` requirement)
- [x] TallyHelp "Integration Initiated From TPAs" (port 9000, collections, `CREATED/ERRORS`)
- [x] VouchRow "Tally XML voucher format" (envelope, sign convention, zero-sum)
- [x] Tally.ERP 9 Integration Capabilities PDF (XML interface read/write)
- Note: Tally's GSP-based **GST e-invoicing** can also be a *pull source* — historical IRNs could be imported (module 17 M3 uses IRP directly; Tally stays the accountant's channel).

---

## 4. Domain model

```
tally_sync_runs        run_type [import|export|migration], status [running|success|partial|failed],
                       started_at, finished_at, counts_json, error_summary, created_by

tally_import_ledger    entity_type [group|ledger|stock_item|voucher], external_id,
                       tally_name, mapped_name, status [mapped|unmapped|skipped], details_json

tally_coa_mapping      tally_group_name -> local_account_id, direction, is_default,
                       confidence, updated_by (one-time + maintained)

tally_voucher_export   id, local_doc_type, local_doc_id, tally_company,
                       xml_payload, response_xml, status [pending|sent|accepted|rejected],
                       tally_voucher_number, sent_at, error

tally_balance_recon    as_on, tally_ledger, local_account, tally_balance, local_balance,
                       difference, status [balanced|diff|unreconciled]
```

### 4.1 COA mapping strategy
Tally's default groups (e.g. *Sundry Debtors*, *Sundry Creditors*, *Bank Accounts*, *Capital Account*, *Sales Accounts*, *Purchase Accounts*, *Direct/Indirect Expenses & Income*) map to our `chart_of_accounts` templates (module 01). Mapping is **suggested with confidence, confirmed by the accountant**, and can be rerun.

---

## 5. State machines

### 5.1 Sync run
```
pending  --start-->  running
running  --ok-->     success        guard: zero fatal errors
running  --warn-->   partial        guard: some items skipped (unmapped ledgers)
running  --err-->    failed         guard: retryable network/format error
```

### 5.2 Voucher export item
```
pending  --send-->   sent           (HTTP to Tally)
sent     --ok-->     accepted       guard: CREATED=1 && ERRORS=0
sent     --err-->    rejected       guard: error text stored; manual repair + resend
rejected --resend--> pending        (fixed payload)
```

---

## 6. API surface

**All new:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `POST /tally/migrations` | POST | `integration.tally.manage` | start a one-time migration (COA + masters + balances) |
| `GET /tally/migrations/{id}/status` | GET | `integration.tally.read` | progress + mapping queue |
| `POST /tally/coa-map` | POST | `integration.tally.manage` | confirm mapping suggestions |
| `GET /tally/coa-map` | GET | `integration.tally.read` | current mapping |
| `POST /tally/export/vouchers` | POST | `integration.tally.manage` | push local vouchers to Tally (batch) |
| `GET /tally/exports/{id}` | GET | `integration.tally.read` | export run detail |
| `POST /tally/reconcile` | POST | `integration.tally.manage` | pull Tally balances → compare |
| `GET /tally/connections` | GET | `integration.tally.read` | connection health (port 9000 reachable) |
| `POST /tally/settings` | PUT | `integration.tally.manage` | Tally server URL/port, company name |

---

## 7. Business rules

- **TL-01** — Tally never writes into Hertex's ledger; only **import maps masters/balances**, and only with accountant confirmation.
- **TL-02** — Voucher exports are **balanced** (sum to zero) or rejected client-side (TL-07 is the Tally-side guard).
- **TL-03** — Sign convention: debit = `ISDEEMEDPOSITIVE Yes` + negative `AMOUNT`; credit = `No` + positive (module 03 I2 ledger convention preserved in the converter).
- **TL-04** — Masters before vouchers; groups before ledgers (`PARENT`).
- **TL-05** — Every exported voucher is logged with payload + response; nothing is sent untracked.
- **TL-06** — Coexistence mode: Hertex remains the *system of record* for operations; Tally receives vouchers for the accountant's books.
- **TL-07** — A rejected voucher never silently retries; it sits in a repair queue.
- **TL-08** — Opening balances reconcile to **zero difference** at migration close (a `tally_balance_recon` with all zeros) before Hertex goes live on finance.

---

## 8. Accounting impact

Migration correctness IS an accounting matter: the trial balance after import must equal Tally's. Every local ledger balance post-migration must match `tally_balance_recon`. Coexistence exports keep the accountant's Tally books aligned with Hertex operations; drift is surfaced by the reconcile job, not silently accepted.

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally's own imports** | Excel/CSV import | Suggested COA mapping + audit of every voucher | Tally's native import UX |
| **Zoho Books "Tally import"** | One-way migration | Bidirectional (migrate + coexist push) | Zoho's accountant app |
| **ClearTax / migration consultants** | Manual/CSV | Repeatable, audited, self-serve | consulting |
| **SAP B1 migration tools** | Data migration framework | SMB-simple, no consultants | SAP's tooling |

**Differentiator (plan's top moat):** we don't just import — we let the accountant *keep* Tally while Hertex runs operations, with the reconcile job proving they match. That's the retention hook no one else has.

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **COA mapping suggestion** (name/description → local account, with confidence) | accountant confirms mapping | suggestion + confidence, never auto-map (TL-01) |
| 1 | **Balance-diff classification** (why a ledger differs: timing, mapping, missed voucher) | which diff to chase | read-only |
| 2 | "Which vouchers didn't sync to Tally?" | instant resolution | read-only, admin-only |

---

## 11. Non-functional & security

- **Resilience:** Tally may be offline → export queue holds; retry with backoff; a heartbeat checks port 9000.
- Performance: voucher export ≥ 1,000 docs/minute (Tally side is the bottleneck).
- **Security:** Tally HTTP listener has no auth by default — **restrict to localhost/VPN**; connection settings encrypted; payloads logged without secrets.
- RBAC: `integration.tally.*`.
- Audit: every sync run, mapping confirm, and export.

---

## 12. Reporting & analytics

Migration dashboard (COA mapped %, balances reconciled), sync health, export success rate, drift by ledger, reconciliation report (the close checklist for the accountant).

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `invoice.posted`, `purchase.posted`, `payment.posted`, `journal.posted` | out (→ queue) | Tally voucher export |
| Tally balance pull | in | reconcile job |
| Migration job | in/out | COA + masters + balances |

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (client + settings)** | Tally HTTP client (port 9000), connection health, settings | heartbeat; connect test against a real Tally |
| **M2 (export)** | voucher envelope builder (balanced, sign-convention), send/repair queue, response handling | TL-02..05, 07 tests; XML validates |
| **M3 (pull/import)** | export COA + ledgers + stock + balances; mapping suggestions with confidence | TL-01/08; mapping UX flow |
| **M4 (coexistence + recon)** | periodic push, reconcile job, drift report | TL-06/08; reconcile shows zero at close |
| **M5 (migration wizard)** | guided one-time migration end-to-end | a real Tally company imported, TB matches |

Order: **M1 → M2 → M3 → M4 → M5**. M2+M3 can be parallel after M1.

---

## 15. Test plan

- Envelope builder: valid XML, mandatory tags, correct sign convention (M2).
- Balanced voucher: sum-to-zero enforced client-side (M2).
- Rejected voucher lands in repair queue, not retried silently (M2).
- Mapping: ledger named "Sundry Debtors - North" suggests Debtors with confidence (M3).
- Recon: difference shows on the right ledger (M4).
- Live test: import a sample Tally company file (M5, needs a Tally test instance).

---

## 16. Migration & rollout

- Pilot: one accountant's Tally company → import → reconcile to zero → run operations → push back → re-reconcile.
- No cutover cliff: coexistence is the safe default; hard cutover only when the accountant is satisfied.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Tally offline/not running | export queue grows | retry/backoff + heartbeat (M1) |
| Mapping errors → wrong COA | wrong financials | confidence + accountant confirm (TL-01) |
| Sign-convention bug | Tally rejects every voucher | M2 fixture tests + live pilot |
| Port 9000 open to network | unauth Tally access | localhost/VPN + settings encryption |

---

## 18. Definition of Done

- [ ] M1 Tally client + health + settings
- [ ] M2 voucher export (balanced, signed) + repair queue
- [ ] M3 pull/import + COA mapping with confidence
- [ ] M4 coexistence push + reconcile + drift
- [ ] M5 migration wizard (live pilot TB = zero)
- [ ] RBAC, audit, secure connection
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated