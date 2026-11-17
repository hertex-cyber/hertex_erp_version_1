# 09 — Projects & Work Management

**Module owner:** Projects
**Current state:** Project + Task tables with budget/billable fields; **no time tracking, no milestone billing, no link to Finance**
**Date:** 2026-07-17

---

## 1. Purpose & scope

Manages client and internal projects: projects, tasks, effort, billing on time/milestone. Per the strategic plan (§2 row 11) this is a place where we are *already ahead* of Zoho/SAP because the WorkItem model is money-aware — but in this codebase that "money-aware" design is only a set of unused columns.

**In scope:** projects, tasks, estimates vs actuals, billable time, milestone billing into Sales/Finance, resource utilisation.
**Out of scope (v1):** Gantt dependency engine, Kanban boards with WIP limits (v1.5), resource levelling, cross-project portfolio planning, the `HertexFlow` universal WorkItem (separate product — see ADR-001).

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `Project` (`projects`), `Task` (`project_tasks`) | ✅ 2 tables (`projects/models.py`) |
| Project fields | `name, code, description, status, start_date, end_date, budget, client_name, manager_id` |
| Task fields | `title, description, status, priority, assignee_id, estimated_hours, actual_hours, billable_rate, budget_amount, due_date, completed_at, is_billable` |
| CRUD routers | ✅ `projects.project.*`, `projects.task.*` |
| Project summary endpoint | ✅ `GET /projects/{id}/summary` |
| **Time entry** | ❌ `actual_hours` is a plain column — no time-sheet records, no per-day entries, nothing to audit |
| **Billable → invoice** | ❌ `is_billable` + `billable_rate` exist but **nothing ever generates invoice lines** |
| **Milestones** | ❌ |
| **Task dependency** | ❌ |
| **Employee link** | ❌ tasks assign to `users.id`, not `hr_employees.id` — two identities for the same person |
| **Budget tracking vs actual** | 🟡 `budget` and `budget_amount` stored; no variance computation, no cost capture |

**Headline:** the money-aware columns (`billable_rate`, `is_billable`, `budget_amount`, `actual_hours`) are **inert** — no process reads or writes them meaningfully. A project module that cannot bill is a to-do list.

---

## 3. Domain model

### 3.1 Target entities

```
projects
  name, code, description, status [planning|active|on_hold|completed|cancelled],
  start_date, end_date, budget, client_name, manager_id
  + add: customer_id (Sales customer — not client_name string), currency, billing_type [fixed|time_and_material|milestone],
          total_billed, total_cost, health [green|amber|red], is_internal, team_member_ids

project_tasks
  title, description, status [todo|in_progress|blocked|review|done], priority,
  assignee_id, estimated_hours, actual_hours, billable_rate, budget_amount, due_date, completed_at, is_billable
  + add: parent_task_id (subtasks), milestone_id, employee_id (HR), start_date, sequence,
          blocked_reason, actual_cost, invoiced (bool)

NEW:
project_time_entries   task_id, employee_id, entry_date, hours, description, billable,
                       rate, amount, invoiced, invoice_line_id, approved_by_id
project_milestones     project_id, name, due_date, amount, status [pending|reached|billed], invoiced_at
project_task_dependencies  task_id, depends_on_task_id, type [finish_to_start]
project_expenses       project_id, task_id, category, amount, receipt_url, reimbursable, invoiced
```

### 3.2 Identity link (important)
Tasks should reference `hr_employees.id` for assignee (the person), while `users.id` remains the login identity. Today `assignee_id -> users.id` conflates them. Migration: add `employee_id` FK, keep `assignee_id` for backward compat, map in the seeder.

---

## 4. State machines

### 4.1 Project
```
planning  --activate-->  active
active    --hold-->      on_hold     guard: reason
on_hold   --resume-->    active
active    --complete-->  completed   guard: all tasks done or waived, unbilled time resolved
any open  --cancel-->    cancelled   guard: manager approval, no unbilled invoices
```
### 4.2 Task
```
todo        --start-->    in_progress
in_progress --block-->    blocked    guard: blocked_reason
blocked     --unblock-->  in_progress
in_progress --review-->   review
review      --approve-->  done       → completed_at, billable time becomes invoiceable
```
### 4.3 Milestone
```
pending  --reach-->  reached   (deliverable accepted by client)
reached  --bill-->   billed    → Invoice line in Sales/Finance, event 'milestone.billed'
```

---

## 5. API surface

Current: projects CRUD, tasks CRUD, `GET /projects/{id}/summary`.

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/projects/{id}/activate` | POST | `projects.project.update` | lifecycle |
| `/projects/{id}/complete` | POST | `projects.project.update` | lifecycle |
| `/projects/time-entries` | POST | `projects.task.update` | log time |
| `/projects/time-entries/{id}/approve` | POST | `projects.project.update` | timesheet approval |
| `/projects/{id}/milestones` | POST | `projects.project.update` | milestone |
| `/projects/{id}/milestones/{mid}/bill` | POST | `projects.project.update` | create invoice → Sales/Finance |
| `/projects/{id}/unbilled` | GET | `projects.project.read` | unbilled time/expenses |
| `/projects/{id}/profitability` | GET | `projects.project.read` | budget vs actual vs billed |
| `/projects/reports/utilisation` | GET | `projects.project.read` | per employee |

---

## 6. Business rules

- **PJ-01** — Billable time is recorded in `project_time_entries`, never inferred from a column edit; `actual_hours` becomes a derived sum.
- **PJ-02** — Only `approved` time entries can be invoiced.
- **PJ-03** — An entry is `invoiced` at most once; re-invoicing is blocked by `invoice_line_id`.
- **PJ-04** — `billing_type=fixed` bills via milestones; `time_and_material` bills from approved time × rate; `milestone` bills only at milestone reach.
- **PJ-05** — Project profitability = billed revenue − (labour cost from timesheets + recorded expenses).
- **PJ-06** — A project cannot complete with unbilled approved time unless explicitly waived (audited).
- **PJ-07** — Task assignee is an employee (`hr_employees`), not a login user.
- **PJ-08** — Budget overrun > threshold flags project health to red and notifies the manager.

---

## 7. Workflows (end-to-end)

### 7.1 Time-and-materials billing
1. Project created (`billing_type=time_and_material`) linked to a Sales customer.
2. Team logs time → entries `submitted`.
3. Manager approves timesheet → entries `approved`.
4. At period end: `GET /unbilled` → generate invoice from approved entries × rate.
5. Invoice posted in Finance (AR/Revenue) via Sales path → entries marked `invoiced`.
6. Profitability report compares revenue vs labour + expenses.

### 7.2 Milestone billing
1. Milestones defined with amounts summing to contract value.
2. Deliverable accepted → milestone `reached`.
3. `bill` → invoice line → Finance → `milestone.billed`.

---

## 8. Accounting impact

| Event | Accounting |
|---|---|
| Time logged | none (cost accrual optional: labour cost → WIP) |
| Invoice from time/milestone | AR debit / Revenue credit (via Finance) |
| Expense recorded reimbursable | Project expense / accrual; on reimbursement → AP/Bank |

Project labour cost can optionally post WIP: `WIP debit / Labour-absorbed credit` — v1.5. v1 requires only the billing path.

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally + Excel** | Project list, budget | Timesheets + invoice generation in one system | — |
| **Zoho Projects** | Tasks, timesheets, Gantt | Billing directly into the same AR ledger (Zoho Projects bills via Books, separate app) | Zoho's Gantt/dependency depth, resource levelling |
| **SAP B1 (Projects)** | Project costing, billing | Simpler; India-fit; invoice-native | SAP's project-cost accounting, WBS |
| **Odoo Project** | Tasks, timesheets, billing | Money-aware tasks; unified ledger | Odoo's Gantt, recurring tasks |

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Delay risk** — task slip prediction from estimate vs actual velocity | manager reassigns/de-scopes before miss | read-only, explain factors |
| 1 | **Billable leakage flag** — billable tasks with no time entries | manager recovers lost revenue | read-only |
| 2 | "How much unbilled time on project X?", "is project Y over budget?" | instant answer | read-only |
| 3 | **Draft invoice from unbilled time** for approval | manager approves pre-filled invoice | approval + audit (A3) |

---

## 11. Non-functional & security

- Performance: project list < 300 ms; timesheet week view < 300 ms.
- Concurrency: concurrent time entries on the same task/day — allow multiple, sum them.
- RBAC: `projects.project.*`, `projects.task.*` (exists) + add `projects.timeentry.*`.
- Field security: billable rates and cost visible to project managers/finance only (D4).
- Audit: timesheet approval, invoice generation, budget changes.

---

## 12. Reporting & analytics

Project profitability, budget variance, utilisation %, unbilled WIP, milestone billing schedule, task throughput. Materialised views: `projects_profitability`, `projects_utilisation`.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `milestone.billed` | out | Finance, Sales, Analytics |
| `project.completed` | out | HR (resource released), Analytics |
| `task.overdue` | out | Integrations (notify assignee) |
| `invoice.paid` | in | Projects marks milestone/entries paid |

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (time entries)** | timesheet table + approval; `actual_hours` derived | PJ-01/02 tests |
| **M2 (billing)** | unbilled report + invoice generation into Sales/Finance; `invoiced` guard | PJ-03/04 tests; no double-billing |
| **M3 (milestones)** | milestone lifecycle + billing | happy path with Finance |
| **M4 (cost & profitability)** | labour cost + expenses; profitability report | PJ-05 tests |
| **M5 (identity + AI)** | employee link; delay-risk + leakage flags | PJ-07; AI metrics |

Order: **M1 → M2 → M3 → M4 → M5**.

---

## 15. Test plan

- Approved-only billing; double-billing blocked (M2).
- Profitability math on fixture (M4).
- Complete with unbilled time requires waiver (PJ-06).
- Employee vs user assignee works after migration (M5).

---

## 16. Migration & rollout

- Import projects/tasks from CSV; backfill time entries from historical spreadsheets (with a `legacy` flag).
- Cutover: bill from month start only, so no double-billing with the old method.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Billable columns stay inert | revenue leakage | M2 before any client with projects |
| User vs employee identity drift | wrong utilisation | M5 migration |
| Double-billing legacy invoices | client dispute | cutover at period boundary |

---

## 18. Definition of Done

- [ ] M1 time entries + approval
- [ ] M2 unbilled → invoice (no double-billing)
- [ ] M3 milestones → invoice
- [ ] M4 profitability report
- [ ] M5 employee identity + AI flags
- [ ] RBAC, audit, outbox, idempotency
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated