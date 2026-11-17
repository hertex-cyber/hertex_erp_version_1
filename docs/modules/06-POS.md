# 06 — Point of Sale (POS)

**Module owner:** POS
**Current state:** checkout already creates a real `SalesOrder(channel="pos")` + linked `PosSale`; invoice marked paid without settlement journal; no offline queue
**Date:** 2026-07-17

---

## 1. Purpose & scope

The store-floor billing surface. A POS sale *is* a `SalesOrder` with `channel="pos"` (Technical Plan §6) — POS adds a fast terminal to that same order, stock, invoice and ledger. Kerala retail floors have flaky connectivity and impatient queues: the design priority is **speed and offline-tolerance**, with Inventory/Finance consistency guaranteed by the shared `SalesOrder` path.

**In scope:** terminal session (cash drawer), fast checkout, payment capture, receipt, offline queue + sync, returns at the till.
**Out of scope (v1):** storefront (module 19), table/kitchen integration, loyalty, EMV device drivers (integrate via payment gateway module 12).

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `PosSession`, `PosSale`, `PosSaleLine` | ✅ 3 tables (`pos/models.py`) |
| Checkout endpoint | ✅ `router.py:95` `POST /checkout` |
| Creates `SalesOrder(channel="pos")` + links `PosSale.sales_order_id` | ✅ **verified** — D1 is already resolved: `PosSale` is a wrapper, NOT a duplicate order |
| Stock: creates `StockMove(−qty, movement_type="sale")` | ✅ |
| Invoice: creates `Invoice(status="paid", amount_paid=total)` + `post_invoice_journal` | ✅ |
| Session open/close with cash handling | ✅ `open`/`close` endpoints + `closing_cash` |
| Payment methods | single `payment_method` string (cash default) |
| **Stock availability check in checkout** | ❌ no `available` validation — can sell below zero (until module 03 M1/M2) |
| **Cash/AR settlement journal** | ❌ invoice marked paid by fiat; no Cash debit / AR credit journal posted |
| **Offline queue** | ❌ Technical Plan §6 requires queue-and-sync for retail floors |
| **Receipt PDF/print** | ❌ |
| **Returns at till** | ❌ (module 05 M3) |

**Headline gaps:** checkout is fast and correct about *creating* stock/invoice/journal, but (a) never verifies stock before selling, (b) never posts the cash settlement side, (c) has no offline path. The offline requirement was explicit in the plan ("offline-tolerant — queue sales locally and sync", Technical Plan §6).

---

## 3. Domain model

### 3.1 Target entities

```
pos_sessions
  terminal_name, opened_by_id, opened_at, closed_at, opening_cash, closing_cash, status [open|closed]
  + add: terminal_id (hardware), expected_closing_cash, declared_closing_cash, discrepancy,
          cash_sales_total, card_sales_total, upi_sales_total, notes

pos_sales   (kept as the thin POS wrapper; the ledger lives on SalesOrder — MA D1 resolved)
  session_id, sales_order_id, sale_number, customer_id, subtotal, tax, total,
  payment_method [cash|card|upi|mixed], status, notes
  + add: offline_id (uuid created on device), sync_status [local|synced|failed],
          receipt_number, cashier_id, items_count, discount, tendered_amount, change_given

pos_sale_lines
  sale_id, product_id, quantity, unit_price, tax_rate, line_total
  + add: product_name_snapshot, hsn_code (snapshot for the receipt), barcode

NEW: (client-side/local storage + server table on sync)
pos_offline_queue       device_id, offline_id, payload_json, created_at, status [pending|synced|conflict]
```

### 3.2 Why `pos_sales` stays (not deleted)
POS needs fast terminal-specific state (cash drawer, tendered/change, offline sync) that doesn't belong on an `Accounts`-facing `SalesOrder`. Keeping `pos_sales.sales_order_id` as the single link means: **one ledger, one stock record, one invoice** — while POS keeps its own UX state. This is the correct reading of the plan's "POS is a SalesOrder", and the current code already does it.

---

## 4. State machines

### 4.1 Session
```
open    --cash-in-->   open   (opening float recorded)
open    --checkout-->  open   (sales accrue to session)
open    --close-->     closed guard: all sales in session already fulfilled/synced
                       → compute expected cash vs declared; discrepancy flagged
```
### 4.2 Sale (device → server)
```
local_draft  --checkout-->  local_completed   (device, offline-ready)
local_completed --queue-->  queued            (offline)
queued       --sync-->      synced            → creates SalesOrder+StockMove+Invoice+journal (same path as online)
synced       --conflict-->  conflict          (stock/reprice changed since sale) → manual resolve
```
Online checkout bypasses the queue: `local_completed → synced` in one request.

### 4.3 Payment
```
due  --cash-->  paid   (tendered/change computed)
due  --card-->  paid   (external auth ref)
due  --upi-->   paid   (UPI ref)
due  --mixed--> paid
```

---

## 5. API surface

Current: `POST /pos/checkout` (+ `POST /pos/sessions`, `POST /pos/sessions/{id}/close`, `GET /pos/sales`).

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/pos/checkout` | POST | `pos.sale.checkout` | add stock availability check + settlement journal |
| `/pos/offline/sync` | POST | `pos.sale.checkout` | batched queued sales from device |
| `/pos/offline/conflicts` | GET | `pos.sale.read` | list sync conflicts |
| `/pos/sales/{id}/receipt` | GET | `pos.sale.read` | PDF/HTML receipt (module 19-docs) |
| `/pos/sales/{id}/refund` | POST | `pos.sale.checkout` | till return → module 05 M3 credit note |
| `/pos/sessions/{id}/report` | GET | `pos.sale.read` | Z-report (sales, methods, discrepancies) |

---

## 6. Business rules

- **PS-01** — A POS sale always writes a `SalesOrder(channel="pos")` and links `PosSale.sales_order_id` (already true).
- **PS-02** — Checkout validates stock availability server-side; below `available`, the sale is refused unless override (module 03).
- **PS-03** — Checkout posts the **cash settlement**: Cash debit / AR credit (inline with invoice post). Currently missing.
- **PS-04** — Invoice is `status="paid"` but the journal must reflect the payment method (cash → Cash account; card → Bank-clearing).
- **PS-05** — Offline sales get a client-generated `offline_id`; sync is idempotent by that id.
- **PS-06** — A session can only close after all its sales are synced; expected cash vs declared reconciled.
- **PS-07** — Return at till requires an approved return (module 05) and writes a credit note (module 17).
- **PS-08** — Receipt prices snapshot product fields at sale time (mutating a product later never rewrites history).

---

## 7. Workflows (end-to-end)

### 7.1 Online checkout (current, plus PS-03)
1. Scan product → server resolves price/stock → validate available (PS-02).
2. Payment captured (cash/card/UPI) → checkout txn:
   - `SalesOrder(channel=pos, status=fulfilled)` + lines
   - `StockMove(−qty)` (module 03)
   - `Invoice(status=paid)` + `post_invoice_journal` (AR/Revenue) **+ Cash/Bank settlement line (PS-03)**
   - `PosSale` wrapper + `PosSaleLine`s, `pos.sale.completed` event
3. Receipt generated → printed/sent via WhatsApp (module 12).

### 7.2 Offline checkout (new)
1. Device in offline mode → checkout computes totals locally → stored in `pos_offline_queue` with `offline_id`.
2. On reconnect → `POST /pos/offline/sync` with the batch → each runs the same path as online (idempotent by `offline_id`).
3. Conflicts (stock/reprice) → held for manual resolution (PS-05).

---

## 8. Accounting & stock impact

| Event | Stock | Accounting |
|---|---|---|
| Online checkout | −qty | AR→Cash/Bank settlement; COGS (module 03) |
| Offline sync | −qty (at sync) | same as online |
| Refund | +qty | credit note (module 17) |

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally + Excel** | Billing on a counter | Fast scan, live stock, receipts, cash drawer | Tally's flexibility |
| **Zoho POS** | Terminal, catalog, payments | Offline queue; same DB as Inventory/Finance | Zoho's loyalty/marketing breadth |
| **SAP B1 (POS)** | POS transactions post to GL | Offline-tolerant; receipts via Engage | SAP's retail integrations |
| **Odoo POS** | POS sessions, cash control | Offline-first (Odoo POS is flaky offline); simpler | Odoo's kitchen/table management |

**Differentiator:** offline tolerance + live single-DB stock is exactly what a Kerala retail floor needs and what every competitor's POS struggles with offline.

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Fast-moving item suggestions** at checkout (frequency from POS history) | cashier upsells/restocks faster | suggestions only |
| 1 | **Till discrepancy flag** (expected vs declared cash recurring) | manager investigates before Z-report | read-only |
| 3 | **Auto reorder when POS sales push stock to reorder level** (via `stock.low` → Procurement) | buyer approves pre-filled PO | approval chain (A3) |

---

## 11. Non-functional & security

- **Offline:** local storage (IndexedDB/SQLite in device app) with manual + automatic sync; never lose a sale.
- **Performance:** checkout p95 < 800 ms (cashier waits); offline checkout < 100 ms locally.
- **Concurrency:** two terminals same product → stock lock (module 03); credit-check for credit customers.
- RBAC: `pos.session.*`, `pos.sale.checkout`, `pos.sale.read`; cashier sees only own session.
- Audit: every checkout, refund, session close, discrepancy logged.

---

## 12. Reporting & analytics

Z-report per session, sales by hour/product/cashier, payment-method mix, returns rate, stock-movement-from-POS. Materialised view (module 13): `pos_sales_daily`.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `pos.sale.completed` | out | Finance, Inventory, Analytics, Integrations (receipt via Engage) |
| `pos.session.closed` | out | Finance (if cash deposited), Analytics |
| `stock.low` | in | reorder via Procurement |

External: payment gateway (Razorpay/PayU — module 12), receipt printer (web → thermal via browser lib), (v2) UPI deep links.

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (settlement + stock guard)** | cash/card settlement journal (PS-03); stock availability validation (PS-02) | no false "paid"; no oversell |
| **M2 (offline queue)** | local queue, `/offline/sync`, idempotency, conflicts | PS-05/06 tests; kill-network test |
| **M3 (sessions & Z-report)** | expected vs declared cash, Z-report endpoint | PS-06 tests |
| **M4 (refund + receipts)** | till refund via module 05/17; PDF/WhatsApp receipt | PS-07/08 tests |

Order: **M1 → M2 → M3 → M4**.

---

## 15. Test plan

- Stock guard: sale of last unit at two terminals → one succeeds (M1).
- Settlement: cash sale posts Cash debit / AR credit; card posts Bank-clearing (M1).
- Offline: queue → sync → same state as online; duplicate sync idempotent (M2).
- Conflict: price changed while offline → flagged (M2).
- Session close with discrepancy (M3); refund → credit note (M4).

---

## 16. Migration & rollout

- Tally: opening float, POS sales history not imported (only totals into opening GL).
- Cutover: install terminals, train cashiers, run parallel with manual billing for a week.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Offline queue never built (M2 skipped) | plan's explicit requirement unmet | release blocker for POS |
| Settlement missing | cash books wrong | M1 blocker, PS-03 |
| Sync conflict lost | duplicate/omitted sales | conflict queue + manual resolve |

---

## 18. Definition of Done

- [ ] M1 settlement journal + stock guard (PS-02/03 green)
- [ ] M2 offline queue + idempotent sync (network-kill test)
- [ ] M3 sessions + expected/declared cash + Z-report
- [ ] M4 refund + receipt (PDF/WhatsApp)
- [ ] RBAC, audit, idempotency, outbox
- [ ] Playwright happy path + demo screen (cashier flow)
- [ ] Conformance row updated