# 13 — Analytics & Business Intelligence

**Module owner:** Analytics
**Rank:** "adequate" module (`Best-Product-Plan §3`) — materialised views + clean charts are enough; **do not build a competing BI tool**
**Current state:** one live-computed `dashboard_payload` with 8 KPIs; no materialised views, no scheduled refresh, no cross-period comparison
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns cross-module reporting: the executive dashboard, KPI computation, saved reports, and the data layer (materialised views) that feeds them. Analytics reads every module and writes none (Invariant I1: no copies, no separate warehouse in v1).

**In scope:** dashboard KPIs, trend series, saved reports, materialised views + refresh schedule, export (CSV/XLSX), per-module report endpoints.
**Out of scope (v1, explicit):** a drag-drop report builder, a data warehouse, predictive analytics beyond the AI module, embedded BI (Power BI/Tableau connectors is v2), ad-hoc SQL console.

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `analytics/service.py` | ✅ 234 lines — `dashboard_payload` + helpers |
| KPIs computed live | ✅ `revenue`, `receivables`, `payables`, `cash_collected`, `pipeline_value`, `low_stock_count`, `stock_value`, `open_deals`, `lead_count`, `open_tickets`, `active_projects` |
| Dashboard endpoint | ✅ `GET /analytics/dashboard` |
| Tenant scoping helper `_scope` | ✅ `service.py:19` |
| **Materialised views** | ❌ none — every dashboard load runs 10+ aggregate queries against live tables |
| **Scheduled refresh** | ❌ no Celery beat (no workers exist at all) |
| **Historical comparison** | 🟡 `revenue_trend` exists; no period-over-period delta |
| **Saved reports / scheduling** | ❌ |
| **Export** | ❌ |
| **Per-module deep reports** | 🟡 each module has a couple of endpoints; no unified report registry |

**Headline:** the dashboard works but is **expensive and shallow** — live aggregates that will degrade as tables grow, with no history, no drill-down, and no schedule. The Technical Plan's Sprint 8 explicitly calls for materialised views refreshed nightly.

---

## 3. Domain model

Analytics owns little data; it owns the **views** and the report definitions.

### 3.1 Materialised views (target)

```
mv_finance_trial_balance      account_id, code, name, type, debit, credit, balance, as_of
mv_finance_aged_receivables   customer_id, bucket_0_30, bucket_31_60, bucket_61_90, bucket_90_plus
mv_finance_aged_payables      vendor_id, same buckets
mv_finance_cashflow_daily     day, inflow, outflow, net
mv_inventory_stock_levels     product_id, warehouse_id, on_hand, reserved, available, value
mv_inventory_valuation        product_id, category, qty, avg_cost, total_value
mv_sales_daily                day, channel, orders, revenue, discount, tax
mv_sales_by_product           product_id, qty_sold, revenue, cogs, margin
mv_procurement_grni_aging     vendor_id, po_id, received_value, age_days
mv_crm_pipeline               stage_id, owner_id, count, value, weighted_value
mv_crm_conversion_funnel      stage_from, stage_to, count, rate
mv_support_sla_compliance     priority, total, breached, compliance_pct
mv_hr_headcount               department_id, employment_type, count, total_salary
mv_projects_profitability     project_id, budget, billed, labour_cost, margin
mv_marketing_campaign_perf    campaign_id, sent, delivered, converted, revenue, roas
```

Refresh: nightly via Celery beat; on-demand refresh endpoint (permission-gated) for a specific view.

### 3.2 Report registry (config, not code)
```
analytics_reports   key, name, module, view_name (or query builder), params_schema,
                    default_sort, columns (JSON), owner_permissions, is_scheduled
```
This makes "add a report" a data change, not a deploy — the right level for an adequate module.

### 3.3 Saved reports
```
analytics_saved_views   user_id, report_key, name, filters (JSON), shared (bool)
analytics_schedules     report_key, cron, recipients, format [csv|xlsx|pdf], is_active
```

---

## 4. State machines

Analytics has no documents, but two background flows need explicit states:

### 4.1 View refresh job
```
scheduled  --start-->  running
running    --ok-->     completed   (record refreshed_at + row count)
running    --fail-->   failed      (record error; alert; keep last good snapshot)
failed     --retry-->  running
```
### 4.2 Scheduled report delivery
```
queued   --generate--> generating
generating --send-->   sent        (email/WhatsApp with attachment)
generating --fail-->   failed
```

---

## 5. API surface

Current: `GET /analytics/dashboard`.

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/analytics/dashboard` | GET | `analytics.dashboard.read` | (exists) — read from views |
| `/analytics/reports` | GET | `analytics.dashboard.read` | report registry |
| `/analytics/reports/{key}` | GET | `analytics.dashboard.read` | run a report with filters |
| `/analytics/reports/{key}/export` | GET | `analytics.dashboard.read` | CSV/XLSX |
| `/analytics/saved-views` | CRUD | `analytics.dashboard.read` | personal/shared views |
| `/analytics/schedules` | CRUD | `analytics.dashboard.read` | scheduled delivery |
| `/analytics/views/refresh` | POST | `system.settings.manage` | on-demand refresh (single view) |
| `/analytics/views/status` | GET | `system.settings.manage` | freshness per view |

---

## 6. Business rules

- **AN-01** — Analytics reads only; it never writes business data (I1). Exception: its own views/schedules.
- **AN-02** — Every tenant-scoped view filters by `tenant_id`; a superadmin sees all, a tenant user sees one.
- **AN-03** — Dashboard KPIs come from materialised views, not live aggregates (except small tables).
- **AN-04** — A stale view is labelled with `refreshed_at`; if refresh failed, show last-good data, never a blank.
- **AN-05** — Exports respect the same RBAC as the on-screen report; no export of a column the user can't see.
- **AN-06** — Report drill-down links to source documents (invoice/order/ticket) by id.
- **AN-07** — All monetary reports disclose currency.

---

## 7. Workflows (end-to-end)

### 7.1 Executive dashboard
1. Celery beat refreshes views nightly (03:00 tenant-local).
2. `GET /analytics/dashboard` reads views → KPIs + trend + freshness stamp.
3. Drill-down from a KPI → module list endpoint with pre-applied filter.

### 7.2 Scheduled weekly report
1. Schedule configured (report + cron + recipients).
2. Beat enqueues → generate from view → export → deliver via email/WhatsApp.
3. Failure alerts the owner.

---

## 8. Accounting impact

None. Analytics must **never** become a source of truth for money — if a report disagrees with the ledger, the ledger wins (BR-10 in module 01).

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally + Excel** | Reports per module | Cross-module dashboard from one DB | Excel's flexibility |
| **Zoho Analytics** | Dashboards, scheduled reports | Zero-setup cross-app (Zoho needs to assemble apps) | Zoho's query builder, ML insights |
| **SAP B1 (Crystal/BO)** | Financial + operational reports | Simpler, faster, self-serve | SAP's enterprise BI, BW |
| **Odoo** | Pivot/graph/cohort views | Cleaner KPI layer | Odoo's pivot builder breadth |
| **Power BI / Tableau** | — | We are not competing; we export | full BI platform |

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **KPI anomaly detection** (revenue dip, receivables spike) | exec asks "why" | read-only, explain via contributing docs |
| 1 | **Forecast series** (revenue/cash next 90 days) | planning decisions | confidence band; view-based |
| 2 | "Ask Hertex" routed here (module 14) | instant answer | read-only |
| 3 | **Narrative digest** ("here's what changed this week") to owner via WhatsApp | owner reads 3 lines instead of a dashboard | generated from views only; no freeform SQL |

Per plan §2.4: the digest must *change a decision* — include one recommended action (chase receivables, reorder SKU), not just description.

---

## 11. Non-functional & security

- Performance: dashboard p95 < 500 ms (views); report < 5 s or async with job status.
- Refresh: full nightly refresh < 10 min at 5M rows; incremental where possible.
- RBAC: `analytics.dashboard.read`, `analytics.report.read`, `analytics.report.export`.
- Field security: salary columns hidden from non-HR (D4) even in aggregate exports where identifiable.
- DPDP: reports containing personal data are access-logged.

---

## 12. Reporting & analytics (self-referential)

View freshness, query latency, report usage, most-used reports, failed refreshes.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `invoice.posted`, `invoice.paid` | in | invalidate finance views |
| `order.fulfilled`, `pos.sale.completed` | in | invalidate sales views |
| `grn.received`, `stock.low` | in | invalidate inventory views |
| `ticket.sla_breached` | in | invalidate support views |
| `payroll.processed` | in | invalidate HR views |

Optional export to Power BI/Google Data Studio (v2, low priority per plan).

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (views)** | materialised views for finance/inventory/sales; dashboard reads views | AN-03/04 tests; dashboard < 500 ms at scale |
| **M2 (refresh)** | Celery beat + invalidation on events + freshness status | AN-04 tests; stale label correct |
| **M3 (report registry)** | config-driven reports + filters + drill-down | AN-06 tests |
| **M4 (export + schedules)** | CSV/XLSX export with RBAC; scheduled delivery | AN-05 tests |
| **M5 (AI)** | anomaly + narrative digest | decision-changing digest verified |

Order: **M1 → M2 → M3 → M4 → M5**. M1 depends on Alembic existing.

---

## 15. Test plan

- Dashboard equals the sum of ledger (reconciliation test).
- Tenant isolation on every view.
- Refresh failure keeps last-good data (AN-04).
- Export respects field masking (AN-05).
- Scheduled report delivers and retries.

---

## 16. Migration & rollout

- Create views after the schema stabilises (post-M1 migrations).
- Backfill: none needed — views derive from live tables.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Live aggregates at scale | dashboard times out | M1 views before volume grows |
| Report disagrees with ledger | trust collapse | AN-03 + reconciliation test |
| Gold-plating a BI tool | wasted capacity (plan warning) | explicit non-goals |

---

## 18. Definition of Done

- [ ] M1 materialised views + dashboard on views
- [ ] M2 scheduled refresh + freshness labelling
- [ ] M3 report registry + drill-down
- [ ] M4 export + schedules (RBAC enforced)
- [ ] M5 anomaly + decision-changing digest
- [ ] RBAC + field masking + audit
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated