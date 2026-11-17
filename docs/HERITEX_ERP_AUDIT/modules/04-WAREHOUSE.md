# 04 — Warehouse Management

**Module owner:** Warehouse (inventory-adjacent)
**Current state:** warehouse + bin tables exist; no putaway, no picking, no barcode, no bin-level stock
**Date:** 2026-07-17

---

## 1. Purpose & scope

Manages *where* stock physically lives: warehouses, bins, putaway, picking/packing/shipping, cycle counts, and delivery challans. Warehouse is the physical-world half of Inventory: Inventory says *how much*, Warehouse says *where*, and the two must never disagree.

**In scope:** warehouse/bin hierarchy, bin-level stock (moves carry `bin_id`), receiving-putaway, order-picking, delivery challans, cycle counts, barcode scanning.
**Out of scope (v1):** full pick-pack-ship automation with carriers, WMS-grade wave planning, RFID, voice picking, yard management.

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `Warehouse` (`warehouses`), `Bin` (`warehouse_bins`) | ✅ 2 tables (`warehouse/models.py`) |
| Warehouse fields | `name, code, address, city, state` |
| Bin fields | `warehouse_id, code, name` |
| CRUD routers | ✅ `warehouse.warehouse.*`, `warehouse.bin.*` |
| `StockMove.bin_id` (per-move bin) | ✅ exists (`inventory/models.py:58`) |
| StockMove references a bin at creation | 🟡 only GRN sets warehouse; no bin assignment, no putaway logic |
| Bin-level stock report | ❌ `stock-levels` aggregates by warehouse only, ignores bin |
| Picking/packing/shipping | ❌ |
| Delivery challans | ✅ created in Sales `fulfill_order` (`sales_delivery_challans`) — but there is **no challan API** beyond it |
| Barcode scanning | ❌ (barcode field exists on Product only) |
| Cycle counts | ❌ |

**Headline gap:** bin infrastructure exists but is **inert** — nothing assigns stock to a bin, reads bin-level availability, or generates picking work. A warehouse module that can't tell you which bin the item is in is just a folder structure.

---

## 3. Domain model

```
warehouses
  name, code, address, city, state
  + add: is_active, is_default, contact_phone, timezone, allow_negative (delegated from product)

warehouse_bins
  warehouse_id, code, name
  + add: zone, aisle, rack, level, is_pickable, is_storage, max_weight, is_active

inventory_stock_moves.bin_id   (already exists) — now required for storage moves, nullable for accounting moves

NEW:
warehouse_putaway_rules     warehouse_id, category_id (or product), from_location, to_bin_id, priority
warehouse_pickings          picking_number, order_id, warehouse_id, status, picked_by, picked_at,
                            packed_by, packed_at, shipped_by, shipped_at
warehouse_picking_lines     picking_id, product_id, bin_id, qty_picked, qty_requested
warehouse_cycle_counts      count_number, warehouse_id, status, counted_by, counted_at, variance_total
warehouse_cycle_count_lines count_id, bin_id, expected_qty, counted_qty, variance
```

---

## 4. State machines

### 4.1 Picking (order fulfilment)
```
created      --release-->   ready        (fulfilment request lands here)
ready        --pick-->      picked       guard: all lines have a source bin with enough stock
picked       --pack-->      packed       guard: qty_picked == qty_requested per line
packed       --ship-->      shipped      → StockMove(−qty, movement_type=sale, bin_id) + DeliveryChallan
any non-shipped --cancel--> cancelled    → release reservation, no moves
```
### 4.2 Cycle count
```
draft      --assign-->   in_progress
in_progress --count-->   counted      (lines recorded)
counted    --approve-->  approved     guard: variance < tolerance OR manager sign-off → adjustment moves (module 03)
counted    --recount-->  in_progress  (if variance > tolerance and recount needed)
```

---

## 5. API surface

Current: `warehouses` CRUD, `bins` CRUD.

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/warehouse/pickings` | POST | `warehouse.picking.create` | create picking from a SalesOrder |
| `/warehouse/pickings/{id}/pick` | POST | `warehouse.picking.update` | record picks (barcode-aided) |
| `/warehouse/pickings/{id}/pack` | POST | `warehouse.picking.update` | pack |
| `/warehouse/pickings/{id}/ship` | POST | `warehouse.picking.update` | ship → moves + challan |
| `/warehouse/putaway-rules` | CRUD | `warehouse.bin.update` | receiving → bin placement |
| `/warehouse/cycle-counts` | POST | `warehouse.cycle_count.create` | new count |
| `/warehouse/cycle-counts/{id}/approve` | POST | `warehouse.cycle_count.approve` | approve variance → adjustments |
| `/warehouse/bins/{id}/stock` | GET | `warehouse.bin.read` | bin-level on-hand |
| `/warehouse/reports/putaway` | GET | `warehouse.bin.read` | pick-face utilisation |

---

## 6. Business rules

- **WH-01** — Bin belongs to exactly one warehouse (FK).
- **WH-02** — Every storage move (`receipt`, `sale`, `transfer`, `adjustment`) sets `bin_id`; a move without a bin is invalid for storage products.
- **WH-03** — Available stock is per `(product, bin)`; aggregate up to warehouse for `on_hand`.
- **WH-04** — A picking is only `packed` when every line's `qty_picked == qty_requested`.
- **WH-05** — Shipping a picking writes the out-moves and a `DeliveryChallan` atomically (one transaction).
- **WH-06** — Cycle count variance above tolerance requires manager approval before it becomes adjustment moves.
- **WH-07** — Putaway rules are evaluated in priority order; the highest-priority matching rule places the goods.
- **WH-08** — A bin flagged `is_pickable=false` cannot be a pick source (storage-only).

---

## 7. Workflows (end-to-end)

### 7.1 Receive → putaway
1. GRN received (module 02) → `StockMove(+qty)` at warehouse.
2. Putaway rule picks a bin by product/category → creates a second move? **No** — putaway is a bin-assignment on the receiving move or a follow-up move to the bin.
3. Bin-level stock now accurate for picking.

### 7.2 Order → pick → pack → ship
1. Sales order fulfilled (module 05) → `Picking` created.
2. Picker scans barcodes → lines picked from bins.
3. Packed → shipped → out-moves + challan → stock down, bin stock down.

### 7.3 Cycle count
1. Count created for a bin range.
2. Count recorded → variances computed.
3. Approve (within tolerance or manager) → adjustment moves → bin stock corrected.

---

## 8. Stock & accounting impact

| Event | Stock effect | Accounting |
|---|---|---|
| Putaway to bin | (no value change) | none |
| Shipment (picking) | −qty at bin | COGS / Stock (module 03) |
| Cycle count variance | ±qty | Adjustment gain/loss (module 03) |
| In-transit transfer | −src +dest | none |

Warehouse never creates journal entries directly — all money passes through Inventory's moves (I3).

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally/Excel** | Warehouse lists | Real bin-level stock + barcode picking (Tally has neither) | — |
| **Zoho Inventory** | Warehouse, transfer orders, pick/pack/ship | Same-DB integration with orders; challans; cycle counts | Zoho's shipping carrier integrations, marketplace sync |
| **SAP B1** | Warehouse, bin locations, picking | Lighter WMS; challan-native (India); putaway rules | SAP's full WM, RF scanning, wave planning |
| **Odoo** | Operations types, putaway, Barcode app | Simpler model; India delivery challans | Odoo Barcode app breadth, DSU, cross-docking |

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Bin layout optimisation** — suggests which bin for incoming goods based on frequency of past picks | putaway default changes | suggestions only; rule override always available |
| 1 | **Pick-face congestion flag** — bins near capacity / high-pick bins | reallocate bins | read-only |
| 3 | **Auto-suggest bin for putaway** as a default in the rule engine | receiving clerk accepts suggestion | rule engine still governs (A3) |

Keep AI light here — warehouse is an operational module, not a differentiator (`Best-Product-Plan §3`).

---

## 11. Non-functional & security

- **Concurrency:** picking lines lock bins; two pickers on the same bin → one waits (row lock on bin stock).
- **Idempotency:** ship endpoint is idempotent (double-ship blocked by `picking.status != shipped`).
- **Performance:** bin stock < 200 ms at 100k bins; picking creation < 300 ms.
- RBAC: add `warehouse.picking.*`, `warehouse.cycle_count.*`; warehouse staff see only their warehouse (tenant + warehouse scoping).
- Audit: every pick/pack/ship step recorded (who, when, bin).

---

## 12. Reporting & analytics

Bin utilisation, pick efficiency (lines/hour), putaway accuracy, cycle count variance trend, backorder report. Materialised views (module 13): `warehouse_bin_stock`, `warehouse_picking_throughput`.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `picking.shipped` | out | Sales (order → dispatched), Finance (if pre-payment release), Integrations (customer notify) |
| `order.fulfilled` | in | creates picking |
| `cycle_count.approved` | out | Inventory (adjustments) |
| `stock.negative_blocked` | in | Warehouse alert (unexpected short pick) |

External: barcode scanners (USB/bluetooth → web app), (v2) courier APIs for labels.

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (bin stock real)** | bin_id on all storage moves; bin-level stock report; putaway rules | WH-02/03 tests; bin stock matches on-hand sum |
| **M2 (picking)** | picking lifecycle; barcode pick UI; ship→moves+challan atomic | WH-04/05 tests; happy path playable |
| **M3 (cycle count)** | count workflow + variance approval → adjustments | WH-06 tests |
| **M4 (polish)** | putaway optimisation AI (Tier 1), reporting | metrics live |

Order: **M1 → M2 → M3 → M4**.

---

## 15. Test plan

- Bin stock = sum of bin moves (M1).
- Picking: partial pick can't pack; overship blocked; double-ship blocked (M2).
- Atomicity: ship failure leaves order un-shipped and no partial moves (M2).
- Cycle count variance: over tolerance requires manager (M3).
- Barcode: scan wrong product rejected (M2).

---

## 16. Migration & rollout

- Import warehouses/bins from a CSV; initial stock at default bin or `unassigned` bin.
- Cutover: count first, then enable picking.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Bin data drift (moves without bin) | picking blind | WH-02 enforced at DB + app |
| Picking bypass (staff ship without picking) | stock wrong | single ship path via picking; challan tied to picking |
| Cycle count never done | perpetual drift | scheduled counts + report |

---

## 18. Definition of Done

- [ ] M1 bin-level stock real (WH-02/03 green)
- [ ] M2 picking lifecycle + barcode + atomic ship
- [ ] M3 cycle counts with variance approval
- [ ] RBAC, audit, idempotency, outbox verified
- [ ] Playwright happy path (receive→pick→pack→ship)
- [ ] Conformance row updated