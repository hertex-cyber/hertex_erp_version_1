# 03 — Inventory (Stock Ledger & Valuation)

**Module owner:** Inventory
**Rank:** core structural module — owns Invariant I2, the single most-referenced rule in the system
**Current state:** products/categories/stock moves exist; no valuation, no reservation, no transfer, no UoM conversion
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns the product master and the **stock ledger**. Inventory answers one question at any moment: *how much of product X is in warehouse W, and what is it worth?* Everything that moves goods — GRN, sales fulfilment, POS sale, transfers, adjustments — writes here. Nothing writes a stock quantity directly.

**In scope:** product/category master, unit of measure, stock moves (append-only), stock levels, reorder points, stock adjustments, transfers, valuation, aging, expiry/batch tracking (v1.5).
**Out of scope:** manufacturing/BOM/MRP (explicitly deferred, `Best-Product-Plan §3`), full landed cost (v1.5, ties to Procurement), bin-level picking (module 04), serial-number tracking (v2).

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `Category`, `Product`, `StockMove` | ✅ 3 tables (`inventory/models.py`) |
| Product fields | `sku, name, category_id, uom, sale_price, purchase_price, tax_rate, reorder_level, barcode, hsn_code` |
| Stock levels report | ✅ `router.py:78-118` — `SUM(StockMove.quantity)` grouped by product (I2 honoured) |
| Low-stock report | ✅ `router.py:127` — `on_hand <= reorder_level` |
| StockMove writers | ✅ 3 (sales fulfil, POS checkout, procurement GRN) — **no shadow counters anywhere** |
| **Valuation** | ❌ no value column, no method, no valuation report |
| **Reservations** | ❌ stock is only decremented at fulfilment; no reservation at order time |
| **Transfers** | ❌ no warehouse-to-warehouse move endpoint |
| **Adjustments** | 🟡 possible via raw StockMove CRUD — no guard, no reason code enforcement |
| **UoM conversion** | ❌ `uom` is a free string; no conversion table |
| **Batch/expiry** | ❌ |
| **Negative stock prevention** | ❌ **nothing stops a StockMove that takes stock below zero** |
| **Immutability of moves** | ❌ StockMove has full CRUD incl. PATCH/DELETE — violates append-only |

**Headline gaps:** StockMove is *editable and deletable* through the generic CRUD router, which silently destroys ledger integrity (the whole point of I2). And there is no negative-stock guard, so a fulfilment can drive stock negative without complaint.

---

## 3. Domain model

### 3.1 Target entities

```
inventory_categories
  name, parent_id, description
  + add: default_valuation_method, default_cost_account_id, default_stock_account_id,
         default_sale_account_id   (account mapping per category — Odoo-style, but lighter)

inventory_products
  sku (unique per tenant), name, description, category_id, uom,
  sale_price, purchase_price, tax_rate, reorder_level, barcode, hsn_code
  + add: uom_id -> inventory_uoms, is_storable (bool), track_batch (bool), track_serial (bool),
          shelf_life_days, weight, is_active, standard_cost, last_cost, avg_cost,
          reorder_qty, lead_time_days, preferred_vendor_id, image_url

inventory_stock_moves   (APPEND-ONLY — no update, no delete)
  product_id, warehouse_id, bin_id, movement_type, quantity (+/-), unit_cost,
  reason, reference
  + add: reference_type, reference_id (polymorphic link to source doc),
          balance_after (optional, for audit), reversed_by_id, is_reversed (bool),
          created_by_id (exists via mixin), lot_id/batch_id (v1.5), value (numeric)
```

### 3.2 New tables
```
inventory_uoms            name, code, category [unit|weight|volume], factor_to_base, base_uom_id
inventory_stock_reservations   product_id, warehouse_id, qty_reserved, source_type, source_id,
                               expires_at, status [active|released|consumed]
inventory_stock_adjustments    adjustment_number, warehouse_id, reason_code, notes, status,
                               approved_by_id   (header; lines are stock moves)
inventory_stock_transfers      transfer_number, from_warehouse_id, to_warehouse_id, status,
                               dispatched_at, received_at   (lines = paired moves)
inventory_lots                 product_id, lot_number, mfg_date, expiry_date, quantity
inventory_valuation_snapshots  product_id, warehouse_id, as_of_date, qty, unit_cost, total_value
```

---

## 4. State machines

### 4.1 StockMove (append-only — no state, but lifecycle rules)
```
create  →  posted (always, immediately, atomic)
posted  →  reversed (only via a compensating move; never edited)
```
Constraint: **no UPDATE, no DELETE** on stock moves after insert. Reversal creates a mirror move with `is_reversed=true` on the original.

### 4.2 StockAdjustment
```
draft       --submit-->   pending
pending     --approve-->  approved    guard: approver != creator, reason_code present   → writes StockMoves
approved    --cancel-->   cancelled   guard: within 24h, no downstream docs
```
### 4.3 StockTransfer
```
draft     --dispatch-->  in_transit   guard: source has enough unreserved stock  → out-move + in-transit location
in_transit --receive-->  received     guard: all lines received                 → in-move at destination
in_transit --cancel-->   cancelled    guard: notify warehouse                  → reverse out-move
```
### 4.4 Reservation
```
active   --consume-->  consumed   (fulfilment converts reservation to an out-move)
active   --release-->  released   (order cancelled)
active   --expire-->   released   (TTL, e.g. 30 min for POS holds)
```

---

## 5. API surface

Current: categories CRUD, products CRUD, stockmoves CRUD (⚠ remove PATCH/DELETE), `/stock-levels`, `/low-stock`.

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/inventory/stock-moves` | POST | `inventory.stockmove.create` | append move (validated) |
| `/inventory/stock-moves` | PATCH/DELETE | — | **removed** (append-only, I4) |
| `/inventory/stock-moves/{id}/reverse` | POST | `inventory.stockmove.update` | compensating move |
| `/inventory/reservations` | POST/DELETE | `inventory.stockmove.create` | reserve/release |
| `/inventory/adjustments` | POST | `inventory.stockmove.create` | adjustment header |
| `/inventory/adjustments/{id}/approve` | POST | `inventory.stockmove.update` | approve → post moves |
| `/inventory/transfers` | POST | `inventory.stockmove.create` | transfer |
| `/inventory/transfers/{id}/dispatch` | POST | `inventory.stockmove.update` | dispatch |
| `/inventory/transfers/{id}/receive` | POST | `inventory.stockmove.update` | receive |
| `/inventory/reports/valuation` | GET | `inventory.product.read` | stock value |
| `/inventory/reports/aging` | GET | `inventory.product.read` | how long stock has sat |
| `/inventory/products/{id}/availability` | GET | `inventory.product.read` | on_hand, reserved, available |
| `/inventory/products/import-tally` | POST | `system.tenant.manage` | Tally stock master (18) |

---

## 6. Business rules

- **IV-01** — Stock on hand is **always** `SUM(StockMove.quantity)`; no stored counter (I2).
- **IV-02** — Stock moves are append-only; corrections are reversing moves (I4).
- **IV-03** — A move may not take on-hand below zero unless the product has `allow_negative=true` (default: refuse).
- **IV-04** — `available = on_hand − reserved`; orders reserve; fulfilment consumes the reservation.
- **IV-05** — Every move has a `reference_type`/`reference_id` pointing at its source document; a move with no source is an adjustment and needs a reason code.
- **IV-06** — On-hand is per `(product, warehouse)`; a move with null warehouse is attributed to the default warehouse on write.
- **IV-07** — Reorder point is per product (v1) with an optional per-warehouse override (v1.5).
- **IV-08** — Product SKU is unique per tenant; barcode is unique per tenant when present.
- **IV-09** — `unit_cost` required for receipts; for issues it is derived from the valuation method.
- **IV-10** — Deactivating a product with non-zero stock is refused.
- **IV-11** — Inter-warehouse transfer creates **two** moves (out + in), never an edit of the original.

---

## 7. Workflows (end-to-end)

### 7.1 Receipt → available → sold
1. GRN creates `StockMove(+qty, movement_type=receipt, reference_type=purchase_order)`. *(Procurement)*
2. Stock levels show the increase; reorder report clears if above level.
3. Sales order **reserves** (`qty_reserved += n`), available drops.
4. Fulfilment creates `StockMove(−qty, movement_type=sale, reference_type=sales_order)` and consumes the reservation.
5. On-hand drops; Finance posts AR/Revenue.

### 7.2 Adjustment (physical count)
Count → adjustment header with reason (`damage`, `theft`, `count_variance`) → approve → single move per line → audit.

### 7.3 Transfer
Dispatch (out-move to in-transit) → receive (in-move at destination). Stock is never "in two places": it is in transit, which is a distinct location.

### 7.4 Reorder
`stock.low` event fires when `available <= reorder_level` → Procurement drafts a PO (Tier 3 AI action, module 02/14).

---

## 8. Stock & accounting impact

| Event | Stock effect | Accounting (Finance) |
|---|---|---|
| Receipt (GRN) | +qty at `unit_cost` | Stock debit / GRNI credit (module 02 BR-04) |
| Sale fulfilment | −qty at valuation cost | COGS debit / Stock credit |
| POS sale | −qty at valuation | Cash/AR debit / Revenue credit + COGS |
| Adjustment up | +qty | Stock debit / Adjustment gain |
| Adjustment down | −qty | Adjustment loss / Stock credit |
| Transfer | −src +dest (no net) | none |
| Return to vendor | −qty | AP debit / Stock credit |

**Valuation decision (D5, from MA §12):** adopt the direction Odoo moved to in its 2025 refactor — **no `stock.valuation.layer` table**. Value lives on the move (`unit_cost` × `quantity`), with `avg_cost`/`last_cost` maintained on the product for reporting. COGS is computed at issue time from the product's current method (weighted average v1, FIFO v1.5). This keeps the design simple and matches the direction of the most actively developed open-source ERP.

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally + Excel** | Stock summary, reorder levels, stock valuation | Real ledger (Tally's stock valuation is fragile); multi-warehouse | Tally's godown-without-valuation shortcuts |
| **Zoho Inventory** | Multi-warehouse, transfers, reorder, batch/serial | Append-only ledger with reversals; no drift; same DB as Finance | Zoho's shipping/courier integrations, marketplace syncs |
| **SAP B1** | Item master, warehouse, valuation (FIFO/Moving Avg), cycle count | Simpler model, faster to deploy; identical audit rigour | SAP's MRP, serial tracking depth |
| **Odoo 18** | Product variants, UoM, stock.quant-style availability, valuation | Cleaner UoM model in v1; reservation discipline | Odoo's variants, putaway rules, package tracking |
| **NetSuite** | Multi-location, lot/serial, demand planning | (n/a v1) | full MRP, demand planning |

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Demand forecasting / reorder point suggestion** — moving average or exponential smoothing over `StockMove` history → recommended `reorder_qty` & date | buyer sets reorder levels instead of guessing | show the last 6 periods as evidence (A4) |
| 1 | **Dead-stock / aging flag** — products with no outbound move in N days | manager marks down or stops buying | read-only |
| 2 | "What's below reorder?", "stock value of category X" | instant answer | read-only, scoped |
| 3 | **Auto-draft PO** at reorder point (cross-module with 02) | buyer approves a pre-filled PO | approval chain intact (A3) |

Forecasting is explicitly a *tabular* problem — use statsmodels/scikit-learn, **not** an LLM (A5).

---

## 11. Non-functional & security

- **Concurrency:** reservation and fulfilment must `SELECT … FOR UPDATE` the product+warehouse aggregate to prevent oversell.
- **Idempotency:** every move carries `reference_type`+`reference_id`+a unique constraint to prevent double-posting on retry.
- **Performance:** stock levels p95 < 400 ms at 1M moves (index `(tenant_id, product_id, warehouse_id)`); consider a partitioned or summary view when >5M.
- **Volume:** plan 2–5M moves/year for a mid-size SMB.
- RBAC: `inventory.category.*`, `inventory.product.*`, `inventory.stockmove.*` (exists) + add `inventory.adjustment.approve`, `inventory.transfer.*`.
- Audit: every adjustment with reason + approver; every reversal linked.

---

## 12. Reporting & analytics

Stock on hand by warehouse, available vs reserved, valuation (weighted avg / FIFO), aging buckets, stock turnover ratio, reorder report, negative-stock exception report, movement history per product. Materialised views (module 13): `inventory_stock_levels`, `inventory_valuation`.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `stock.low` | out | Procurement (auto-draft PO), Integrations (notify buyer) |
| `stock.adjusted` | out | Finance (variance posting), Analytics |
| `stock.negative_blocked` | out | Support (alert) |
| `grn.received` | in | creates receipt move |
| `order.fulfilled` | in | creates sale move (currently inline — refactor to handler) |
| `pos.sale.completed` | in | creates sale move |

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (ledger integrity)** | Remove PATCH/DELETE on stock moves; negative-stock guard; reference_type/id; unique idempotency; reversal endpoint | IV-01..IV-05 tests green; impossible to edit history |
| **M2 (reservations)** | Reservation table + available count; reserve on order create; consume on fulfil | No oversell under concurrency (test with 2 parallel fulfils) |
| **M3 (adjustments & transfers)** | Adjustment + transfer workflows with approval | Physical count and transfer post correctly |
| **M4 (valuation)** | `unit_cost` discipline, `avg_cost`, valuation report, COGS posting | Valuation report ties to GL stock account |
| **M5 (UoM + imports)** | UoM table & conversion; Tally product import | Base/case conversion correct; import reconciled |

Order: **M1 (must, integrity) → M2 → M3 → M4 → M5**.

---

## 15. Test plan

- Invariant: `SUM(moves)` equals reported on-hand everywhere (IV-01).
- Append-only: PATCH/DELETE returns 405 (M1).
- Negative stock: fulfilment refused (M1); allowed when `allow_negative`.
- Oversell: 2 concurrent fulfils of last unit → one fails (M2).
- Idempotency: duplicate `reference_id` move rejected.
- Transfer: net stock unchanged; in-transit visible (M3).
- Valuation: after receipt+sale, COGS = qty × avg cost; GL ties (M4).
- UoM: 1 case = 12 pcs conversion applies (M5).

---

## 16. Migration & rollout

- Tally: opening stock + stock groups → categories/products + opening StockMoves at `unit_cost` (module 18).
- Cutover: freeze stock; import; reconcile count vs system; enable movements.
- Backfill: derive `avg_cost` from historical PO prices.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Editable stock moves ship (M1 skipped) | ledger corrupt, Zoho-style drift | release blocker |
| Oversell under concurrency | customer promises unmet | DB-level reservation lock |
| Valuation drift vs GL | balance sheet mismatch | monthly valuation-vs-GL reconciliation report |
| UoM misuse | wrong quantities | conversion table + validation |

---

## 18. Definition of Done

- [ ] M1 append-only + negative guard + idempotency verified
- [ ] M2 reservations prevent oversell (concurrency test)
- [ ] M3 adjustments/transfers with approval + audit
- [ ] M4 valuation report ties to GL stock account
- [ ] M5 UoM conversion + Tally import
- [ ] RBAC, audit, outbox verified
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated