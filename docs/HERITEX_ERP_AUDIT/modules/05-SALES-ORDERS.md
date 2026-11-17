# 05 — Sales / Order Management

**Module owner:** Sales
**Current state:** customer master, sales orders, delivery challans, fulfil→invoice→stock posting exist
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns the order-to-cash core on the revenue side: customer master, sales orders (all channels), fulfilment, delivery challans, and the hand-off to Finance (invoice + AR) and Inventory (out-moves). Every sale — manual, POS, future storefront — is a `SalesOrder` with a `channel`; there is exactly one order table (Invariant I1).

**In scope:** customers, sales orders with pricing/discounts/tax, order lifecycle, fulfilment, challans, returns/credit notes (link to module 17), order reservation.
**Out of scope (v1):** storefront (module 19-storefront deferred), subscriptions/recurring billing, advanced pricing rules (tiered/contract), omnichannel order routing (v1.5 via module 12).

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `Customer` (`customers`), `SalesOrder`, `SalesOrderLine`, `DeliveryChallan` | ✅ 4 tables (`sales/models.py`) |
| Customer fields | `code, name, email, phone, gstin, billing/shipping address, credit_limit, payment_terms` |
| Order fields | `order_number, customer_id, order_date, status, channel, subtotal, discount, tax, total, warehouse_id` |
| Order create with line pricing (`_price_line`) | ✅ `router.py:89` — subtotal/tax/total computed |
| Order CRUD + list by status | ✅ |
| `fulfill_order` | ✅ `router.py:238-319` — StockMove out + DeliveryChallan + Invoice + `post_invoice_journal` + `order.fulfilled` |
| Order reservation | ❌ no reservation (module 03 M2) |
| Returns / credit notes | ❌ |
| Quote→order conversion | ❌ |
| Customer credit-limit check | ❌ field exists, never enforced |

**Headline gaps:** fulfilment is a single monolithic handler (order→stock→invoice→journal all inline) — correct but rigid; no reservation at order time (oversell possible until module 03 M2); no returns path (blocked without module 17's credit notes); no credit-limit enforcement despite the field.

---

## 3. Domain model

### 3.1 Target entities

```
customers
  code, name, email, phone, gstin, billing_address, shipping_address, credit_limit, payment_terms, notes
  + add: is_active, default_warehouse_id, default_price_list_id, currency, tax_registration,
         category (retail/wholesale/corporate), owner_user_id, created_from (deal_id)

sales_orders
  order_number, customer_id, order_date, status, channel [manual|pos|storefront|whatsapp],
  subtotal, discount, tax, total, warehouse_id, notes
  + add: price_list_id, currency, ship_to_address, delivery_method, expected_delivery,
          reserved (bool), placed_by_user_id, source_lead_id, fulfillment_note

sales_order_lines
  order_id, product_id, description, quantity, unit_price, discount, tax_rate, line_total
  + add: reserved_qty, fulfilled_qty, returned_qty, hsn_code, source_quote_line_id

sales_delivery_challans
  challan_number, order_id, dispatched_date, status, warehouse_id, notes
  + add: picking_id, shipped_via, tracking_number, signed_by

NEW:
sales_quotes            quote_number, customer_id, status [draft|sent|accepted|declined|expired],
                        valid_until, subtotal, tax, total, converted_order_id
sales_quote_lines       quote_id, product_id, quantity, unit_price, discount, line_total
sales_returns           return_number, order_id, status [requested|approved|received|completed|rejected],
                        reason_code, notes
sales_return_lines      return_id, order_id_line_id, qty_returned, condition
```

---

## 4. State machines

### 4.1 SalesOrder
```
draft     --submit-->   confirmed    guard: lines valid, stock available to reserve   → reserve
confirmed --fulfil-->   fulfilled    guard: all lines have stock                      → moves, challan, invoice, AR
confirmed --partial-->  partially_fulfilled
fulfilled --return-->   returned     (via module 17 credit note)
any non-fulfilled --cancel-->  cancelled   guard: nothing fulfilled   → release reservation
```
### 4.2 Quote
```
draft   --send-->    sent
sent    --accept-->  accepted   → converts to SalesOrder (channel = source), event 'quote.accepted'
sent    --expire-->  expired
```
### 4.3 Return
```
requested --approve--> approved    (reason + stock check)
approved  --receive--> received    → return StockMove(+qty), credit note (17), event 'return.received'
received  --complete--> completed
requested --reject-->  rejected
```

---

## 5. API surface

Current: customers CRUD, orders CRUD + `/fulfill`, challans CRUD.

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/sales/orders` | POST | `sales.salesorder.create` | with reservation (module 03) |
| `/sales/orders/{id}/submit` | POST | `sales.salesorder.update` | draft→confirmed |
| `/sales/orders/{id}/cancel` | POST | `sales.salesorder.update` | release reservation |
| `/sales/quotes` | POST | `sales.quote.create` | create quote |
| `/sales/quotes/{id}/convert` | POST | `sales.quote.update` | quote→order |
| `/sales/returns` | POST | `sales.return.create` | request return |
| `/sales/returns/{id}/approve` | POST | `sales.return.approve` | approve |
| `/sales/customers/{id}/credit-check` | GET | `sales.customer.read` | available credit |

---

## 6. Business rules

- **SO-01** — All sales are `SalesOrder`s; `channel` distinguishes source. POS writes one (already true).
- **SO-02** — Order prices come from the price list, overridable per line; totals computed server-side (never trust client totals).
- **SO-03** — An order cannot exceed a customer's available credit (credit_limit − outstanding) unless flagged/approved. *(Unimplemented.)*
- **SO-04** — Fulfilment requires stock; insufficient stock → partial or hold, never silent oversell.
- **SO-05** — Fulfilment is atomic: out-moves + challan + invoice + AR journal in one transaction (already true).
- **SO-06** — An order can only be cancelled before any fulfilment; after partial, only a return path exists.
- **SO-07** — A quote expires on `valid_until`; expired quotes can't convert.
- **SO-08** — Returns require an approved request; a received return creates a credit note in Finance (module 17), not a silent edit.
- **SO-09** — GST: B2B orders carry buyer GSTIN; HSN per line (module 17).

---

## 7. Workflows (end-to-end)

### 7.1 Quote → order → cash (target)
1. Quote created → sent → accepted → converted to `SalesOrder` (channel preserved).
2. Order confirmed → reservation locks stock.
3. Fulfil → out-moves + challan + invoice (status=sent) + AR journal.
4. Payment → `invoice.paid` → CRM deal close, Analytics.
5. (Return path via module 17.)

### 7.2 Current (already works, simplified)
`create_order` → `fulfill_order` (monolithic but complete). Verified: StockMove(−qty), DeliveryChallan, Invoice(status=sent), `post_invoice_journal`, `order.fulfilled`.

---

## 8. Accounting & stock impact

| Event | Stock | Accounting |
|---|---|---|
| Confirm (reserve) | reserved +n (no move) | none |
| Fulfil | −n at valuation | AR debit / Revenue credit (via invoice) + COGS |
| Return received | +n | credit note: Sales return / AR credit |
| Cancel | release reservation | none |

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally + Excel** | Sales vouchers, challans | Quotes, reservations, multi-channel in one table | Tally's voucher flexibility |
| **Zoho Books + CRM** | Sales orders, invoices, quotes | One order table across channels; reservation discipline | Zoho's estimate/recurring breadth |
| **SAP B1** | Sales order → delivery → A/R invoice | Lighter; challan-native; instant AR | SAP's full order types & workflow |
| **Odoo** | SO/PO/quotes, invoicing | Simpler reservation + channel model | Odoo's sales teams, pricelist variants |
| **NetSuite** | Order management, fulfilment | (n/a v1) | multi-subsidiary |

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Deal-close likelihood** on orders (age, discount requested, customer history) | sales rep prioritises follow-up | read-only |
| 1 | **Suggested follow-up** when a confirmed order sits un-fulfilled > N days | rep nudges customer / warehouse | suggestion only |
| 2 | "Order status for customer X?", "open orders this week" | instant answer | read-only |
| 3 | **Auto-draft WhatsApp** order confirmation / delivery notice via Engage (module 12) | rep approves send | template allow-list + consent (A3) |

---

## 11. Non-functional & security

- Concurrency: reservation lock (module 03); fulfil idempotent via `status`.
- Performance: order list p95 < 300 ms; fulfil < 500 ms (transaction size).
- RBAC: `sales.customer.*`, `sales.salesorder.*`, `sales.deliverychallan.*` (exists) + add `sales.quote.*`, `sales.return.*`.
- Field security: pricing/cost visible to sales-manager+ only (D4).
- Audit: every status transition (submit/fulfil/cancel/return).

---

## 12. Reporting & analytics

Revenue by channel/period, order-to-cash cycle time, fulfilment time, quote conversion rate, return rate, credit exposure per customer, backorder report.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `order.created` | out | Inventory (reserve), Integrations |
| `order.fulfilled` | out | Finance, Marketing (CAPI), Analytics, Integrations |
| `quote.accepted` | out | CRM (deal stage), Analytics |
| `return.received` | out | Finance (credit note), Inventory (stock-in) |
| `deal.won` | in | Sales creates customer |

External: storefront (deferred) posts into `channel=storefront`; courier APIs (v2).

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (credit + reservation)** | enforce credit_limit; reservation on confirm; release on cancel | SO-03/04 tests; no oversell |
| **M2 (quotes)** | quote lifecycle + conversion | SO-07 tests; happy path |
| **M3 (returns + credit notes)** | return workflow + credit note with module 17 | SO-08 tests |
| **M4 (refactor)** | split monolithic fulfil into event handlers (stock, invoice, AR, notify) | same behaviour, cleaner wiring |

Order: **M1 → M2 → M3 → M4**.

---

## 15. Test plan

- No oversell under concurrency (M1).
- Credit limit: order over limit rejected; approved flag path works (M1).
- Fulfil atomicity: failure mid-way leaves order un-fulfilled and no partial moves (current, keep test).
- Quote expiry (M2); return → credit note (M3).
- Idempotency: double fulfil blocked.

---

## 16. Migration & rollout

- Tally: sales ledger, open invoices, customer master → customers + open orders (module 18).
- Cutover: freeze sales; import; verify AR opening ties.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Oversell (reservation not shipped) | promises unmet | module 03 M2 + SO-04 |
| Returns without credit note | AR overstated | module 17 gate on return receive |
| Client-trusted totals | tax errors | server-side pricing (SO-02) |

---

## 18. Definition of Done

- [ ] M1 credit enforcement + reservation
- [ ] M2 quotes + conversion
- [ ] M3 returns + credit notes
- [ ] M4 event-handler refactor of fulfil
- [ ] RBAC, audit, idempotency, outbox
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated