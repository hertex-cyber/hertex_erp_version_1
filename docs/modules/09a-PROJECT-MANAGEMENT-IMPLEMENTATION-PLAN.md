# Hertex ERP — Project Management Module Implementation Plan

**Status:** planned · **Owner:** backend + frontend + PMO/product · **Date:** 2026-11-18
**Scope:** project portfolios, programs, projects, work-item workflows, Agile planning, Gantt/dependencies, resource capacity with HR integration, timesheets, billing/profitability, risks/issues/goals, intake, automation, reporting, and AI.
**Benchmarks:** Jira/Atlassian, Linear, Asana, Monday.com, ClickUp, Microsoft Planner/Project, Smartsheet, PMBOK Guide Eighth Edition, Agile Practice Guide Second Edition.
**Normative base:** `docs/modules/00-MASTER-ARCHITECTURE.md`; this plan must not contradict invariants I1–I6, D2/D3/D4, AI tiers A1–A5, or the benchmark framework.
**Companion plan:** `docs/modules/08a-HR-IMPLEMENTATION-PLAN.md` — Projects consumes HR employee, skill, leave, attendance, and cost data; it never duplicates HR master data.

---

## 1. Purpose & scope

### 1.1 Purpose

Build a Jira-class work management system that is **ERP-native**: work items, boards, backlogs, sprints, Gantt, dependencies, timesheets, billing, profitability, capacity, risks, goals, automation, and AI all live in the same tenant database as Finance, Sales, Support, Documents, Identity, and HR. The goal is not to clone one tool; it is to combine the best patterns from Jira, Linear, Asana, Monday, ClickUp, Microsoft Planner, and Smartsheet while removing the cross-app sync gap that exists when project execution, people data, time, invoices, and the ledger live in separate products.

The differentiator is the **money-and-people-aware work graph**: a task knows its employee assignee, leave-adjusted capacity, cost rate, billable rate, budget, milestone, dependencies, risk signals, invoice linkage, and journal impact.

### 1.2 In scope

- Portfolio → program → project → epic/initiative → work item → subtask hierarchy.
- Configurable workflows, statuses, transitions, approvals, schemes, custom fields, labels, and templates.
- Scrum backlogs, sprints, Kanban boards with WIP limits, cycle planning, triage, ranking, velocity, and flow metrics.
- Gantt/Timeline, milestones, dependencies (FS/SS/FF/SF), lead/lag, critical path, baselines, and schedule variance.
- Resource roles, skills, employee capacity, leave-aware availability, bookings, workload heatmaps, and demand forecasting.
- Time entries, timesheets, approvals, billable time, expenses, billing runs, invoice proposals, and project profitability.
- Risks, issues, blockers, decisions, change requests, assumptions, dependencies, and status reports.
- Goals/OKRs, project intake, portfolio health, benefits tracking, and governance reviews.
- Comments, mentions, attachments via Documents, activity feed, notifications via Integrations, and customer/team calendars.
- Automation rules, webhooks, Jira/MS Project/CSV import, Git and Support links.
- AI with explicit tiers: prediction/scoring, Ask Hertex queries, and human-approved agents.

### 1.3 Out of scope / deliberately deferred

- Full DevOps product (CI/CD, deploy pipelines, code review); v1 links to GitHub/GitLab by URL/webhook only.
- Full HR performance appraisal; HR plan owns employee lifecycle and payroll.
- Manufacturing MRP/Production planning; governed by master decision D7.
- Generic low-code platform/BPM builder; use the narrow workflow engine from ADR-002.
- Autonomous AI closure of tasks, approval of timesheets, posting of invoices, or reassignment of people.
- Social/chat workspace replacement; use existing Integrations and channel messages.

### 1.4 Relationship to existing docs

`docs/modules/09-PROJECTS.md:9-15` scoped v1 narrowly and deferred Gantt, Kanban, resource levelling, and portfolio planning. This plan supersedes that scope because the user brief explicitly requires a Jira-class project-management module with more capability, AI, and HR integration. The retained baseline is accurate: the current module has only two tables and inert billing columns (`docs/modules/09-PROJECTS.md:18-37`; `backend/app/modules/projects/models.py:13-52`).

---

## 2. Current state (verified from code)

### 2.1 Backend

| Area | Current state | Evidence |
|---|---|---|
| API mounting | Project router is mounted under `/api/v1/projects` | `backend/app/core/config.py:13`, `backend/app/main.py:60`, `backend/app/api/v1/router.py:19,39`, `backend/app/modules/projects/router.py:25` |
| Tables | Only `projects` and `project_tasks` exist | `backend/app/modules/projects/models.py:13-28,31-52` |
| Project fields | `name`, `code`, `description`, `status`, `start_date`, `end_date`, `budget`, `client_name`, `manager_id` | `backend/app/modules/projects/models.py:16-26` |
| Task fields | `project_id`, `title`, `description`, `status`, `priority`, `assignee_id`, `estimated_hours`, `actual_hours`, `billable_rate`, `budget_amount`, `due_date`, `completed_at`, `is_billable` | `backend/app/modules/projects/models.py:34-50` |
| Tenant/audit fields | Both tables inherit framework tenant/soft-delete/created-by mixins | `backend/app/modules/projects/models.py:10,13,31`, `backend/app/db/base.py:16-55` |
| Schemas | CRUD schemas and a summary schema exist; no enum/date validation | `backend/app/modules/projects/schemas.py:11-113` |
| CRUD routers | Generic CRUD for projects and tasks only | `backend/app/modules/projects/router.py:28-59`, `backend/app/core/crud.py:156-307` |
| Custom endpoint | Only `GET /projects/{id}/summary` aggregates task counts, estimated/actual hours, and billable value | `backend/app/modules/projects/router.py:62-87` |
| Service layer | No `projects/service.py`; no domain services or state machine | Module files: `__init__.py`, `models.py`, `router.py`, `schemas.py` |
| Permissions | Only `projects.project.*` and `projects.task.*`; no time entry, billing, resource, risk, or PMO actions | `backend/app/core/permissions_catalog.py:8,10-31,43-58` |
| Seed data | One demo project and three tasks; project sequence seed exists | `backend/app/db/seed.py:27,42,365-385` |
| Migration | Initial schema only; no later project migration | `backend/alembic/versions/6a04e2a77f21_initial_schema.py:500-525,779-809` |
| Invoice model | Finance invoice has customer/source/totals but no line-item table and no `project_id` | `backend/app/modules/finance/models.py:91-108`, `backend/app/modules/finance/schemas.py:95-108` |
| Finance posting | Reusable journal and idempotent invoice posting service exists | `backend/app/modules/finance/service.py:27-32,55-75,78-97,160-231,234-289` |
| Analytics | Only `active_projects` KPI exists | `backend/app/modules/analytics/service.py:14,131-140,216`, `backend/app/modules/analytics/schemas.py:20` |
| AI | A basic project/task intent exists but only answers active project count | `backend/app/modules/ai/service.py:32-33,148-151`; insights have no project rule at `:174-227` |
| Events/workers | No project publisher/subscriber/task exists; generic bus, messaging, and worker seams are available | `backend/app/core/events.py:21-39`, `backend/app/core/subscribers.py:20-106`, `backend/app/modules/integrations/service.py:46-101`, `backend/app/workers/tasks.py:16-80` |

### 2.2 Frontend

| Area | Current state | Evidence |
|---|---|---|
| Pages | Two generic `ResourcePage` wrappers: Projects and Tasks | `frontend/src/pages/resources/projects.jsx:10-44,46-86` |
| Routes | `/projects/projects` and `/projects/tasks` | `frontend/src/App.jsx:52-53,158-159` |
| Nav | Operations group contains Projects and Tasks | `frontend/src/lib/nav.js:109-115` |
| UI capabilities | List/search/filter/create/edit/archive only; no detail view, board, backlog, Gantt, timesheet, risk, or dashboard | `frontend/src/pages/resources/projects.jsx:6-8,10-86`, `frontend/src/components/ResourcePage.jsx:17-31,186-300,417-527` |
| Dashboard | Active-project KPI links to projects | `frontend/src/pages/Dashboard.jsx:115,322` |
| Lookups | Projects and users are available as generic lookups | `frontend/src/lib/lookups.js:17,24,36-44` |

### 2.3 Tests and integration gaps

- No backend test mentions projects, tasks, time entries, timesheets, milestones, billable time, or profitability; indirect seeding only via `backend/app/tests/conftest.py:9-14,17-33,36-56`.
- No frontend test runner or frontend tests exist; `frontend/package.json` has only `dev`, `build`, and `preview` scripts.
- No `project_id` on invoices, no invoice line table, no billing run, no approved-time gate, and no double-billing guard.
- No employee assignee: `assignee_id` and `manager_id` reference `users.id` (`backend/app/modules/projects/models.py:24-26,41-43`) while HR employee identity is `hr_employees.id` (`backend/app/modules/hr/models.py:20-41`).
- No leave-aware or attendance-aware capacity; HR plan adds leave ledgers at `docs/modules/08a-HR-IMPLEMENTATION-PLAN.md:159-160` and reconciled attendance at `:123-125`.
- No project-specific status transition, audit trail, WIP limit, sprint, rank, dependency, risk, issue, goal, or automation model.
- No project events such as `project.completed`, `milestone.billed`, `task.overdue`, `timesheet.approved`, or `resource.overallocated`.
- The current `actual_hours` column is directly editable (`backend/app/modules/projects/models.py:45`, `backend/app/modules/projects/schemas.py:82,96`), so time can be invented without an auditable time entry.

### 2.4 Headline

The current module is a two-table to-do list with money columns that nothing reads. It cannot plan work like Jira, plan schedule like Microsoft Project, manage capacity like Asana/Monday, bill time like ClickUp/Smartsheet, or connect delivery to Finance and HR. The implementation target is a full work-management subsystem, delivered in phases, with the money/people integration as the moat.

---

## 3. Domain model

### 3.1 Ownership rule

Projects owns all `project_*` tables and the two legacy tables `projects` and `project_tasks`. It reads `hr_employees`, `hr_leave_balances`, `hr_attendance`, `hr_salary_structures`, `customers`, `finance_accounts`, `finance_invoices`, `finance_journal_entries`, `users`, `audit_logs`, `number_sequences`, `channel_messages`, and document IDs. It never writes another module's table directly; cross-module effects go through service calls, events, and the outbox.

### 3.2 Core hierarchy

```
portfolio (group of programs/projects, owner, goals, health)
  program (coordinated projects, benefits, dependencies)
    project (customer/internal delivery container)
      project_phase or epic (large outcome)
        work item (story | task | bug | enabler | risk_task | onboarding_task)
          subtask
```

Cross-cutting containers:

- `goal` / `okr` can span portfolios, programs, and projects.
- `sprint` / `cycle` is a timebox applied to teams and work items.
- `board` is a view over work items with columns and WIP limits; it is not a duplicate work-item table.
- `milestone` is a dated deliverable, billable when configured.
- `release` groups work items and milestones for deployment or customer delivery.

### 3.3 Existing tables to extend

#### `projects`

Keep the physical table; add:

- `number` using Settings numbering, `customer_id` FK to Sales `customers`, `program_id`, `portfolio_id`.
- `billing_type` (`fixed`, `time_and_material`, `milestone`, `non_billable`, `internal`), `currency`, `contract_value`, `cost_center_code`, `billing_contact_id`.
- `planned_start_date`, `planned_end_date`, `baseline_start_date`, `baseline_end_date`, `forecast_end_date`.
- `budget_hours`, `budget_cost`, `budget_revenue`, `total_billed`, `total_cost`, `total_expense`, `wip_amount`, `margin_amount`, `margin_percent`.
- `health` (`green`, `amber`, `red`, `unknown`), `health_reason`, `priority`, `methodology` (`agile`, `predictive`, `hybrid`), `is_internal`, `template_id`.
- `manager_employee_id` FK to `hr_employees.id`; keep `manager_id` for login compatibility during migration.
- `status` becomes an enum/check-constrained value governed by a state machine.
- `version` for optimistic locking.

#### `project_tasks`

Keep the physical table as the generic work-item store; add:

- `number` (e.g. `PRJ-123`), `work_item_type` (`epic`, `feature`, `story`, `task`, `bug`, `enabler`, `subtask`), `parent_work_item_id`.
- `employee_id` FK to `hr_employees.id`; keep `assignee_id` as login-user compatibility only.
- `sprint_id`, `board_id`, `board_column_id`, `rank`, `story_points`, `business_value`, `impact`, `confidence`, `effort`.
- `start_date`, `planned_hours`, `remaining_hours`, `actual_cost`, `actual_revenue`, `billable_amount`, `invoiced_amount`.
- `milestone_id`, `release_id`, `blocked_reason`, `blocked_by`, `duplicate_of_id`, `resolved_at`, `resolution`, `reopened_count`.
- `wip_limit_override`, `is_billable` retained, `billable_rate` retained but only written by rate/permission services.
- `version`, `state_changed_at`, `last_activity_at`, `ai_risk_score`.

### 3.4 New Projects-owned tables

#### Work management

- `project_portfolios`: `name`, `code`, `owner_employee_id`, `strategy`, `health`, `status`, `budget`, `currency`.
- `project_programs`: `portfolio_id`, `name`, `code`, `manager_employee_id`, `benefits_json`, `health`, `status`.
- `project_phases`: `project_id`, `name`, `sequence`, `start_date`, `end_date`, `status`.
- `project_sprints`: `project_id`, `number`, `name`, `start_date`, `end_date`, `goal`, `capacity_hours`, `capacity_points`, `status`.
- `project_boards`: `project_id`, `name`, `type` (`kanban`, `scrum`, `timeline`), `wip_enabled`, `status`.
- `project_board_columns`: `board_id`, `name`, `sequence`, `wip_limit`, `status_category` (`todo`, `active`, `done`, `cancelled`).
- `project_work_item_links`: `work_item_id`, `linked_work_item_id`, `link_type` (`blocks`, `is_blocked_by`, `relates_to`, `duplicates`, `causes`, `caused_by`, `clones`).
- `project_labels`: `project_id`, `name`, `color`, `status`.
- `project_work_item_labels`: `work_item_id`, `label_id`.
- `project_custom_fields`: `entity_type`, `code`, `label`, `type`, `options_json`, `required`, `visible_roles`, `status`.
- `project_work_item_field_values`: `work_item_id`, `field_id`, `value_json`, `version`.
- `project_workflow_schemes`: `name`, `entity_type`, `work_item_type`, `statuses_json`, `status_categories_json`, `status`.
- `project_workflow_transitions`: `scheme_id`, `from_status`, `event`, `to_status`, `guard_code`, `required_role`, `required_fields_json`, `side_effects_json`, `status`.
- `project_approvals`: `entity_type`, `entity_id`, `approval_type`, `approver_employee_id`, `status`, `decision`, `decision_at`, `due_at`, `comments`.
- `project_templates`: `name`, `type`, `workflow_scheme_id`, `structure_json`, `checklist_json`, `default_billing_type`, `status`.

#### Planning and schedule

- `project_milestones`: `project_id`, `name`, `due_date`, `amount`, `currency`, `acceptance_criteria`, `status`, `accepted_by_id`, `accepted_at`, `invoice_link_id`.
- `project_dependencies`: `predecessor_id`, `successor_id`, `type` (`FS`, `SS`, `FF`, `SF`), `lag_days`, `status`.
- `project_baselines`: `project_id`, `name`, `approved_by_id`, `approved_at`, `status`.
- `project_baseline_snapshots`: `baseline_id`, `entity_type`, `entity_id`, `snapshot_json`, `captured_at`.
- `project_releases`: `project_id`, `name`, `release_date`, `status`, `work_items_json`.
- `project_change_requests`: `project_id`, `title`, `reason`, `scope_impact`, `cost_impact`, `schedule_impact`, `status`, `approved_by_id`.

#### Time, cost, and billing

- `project_time_entries`: `work_item_id`, `employee_id`, `entry_date`, `hours`, `description`, `billable`, `billable_rate`, `cost_rate`, `source` (`manual`, `import`, `timer`, `mobile`), `external_id`, `status`, `approved_by_id`, `approved_at`, `invoice_link_id`, `version`.
- `project_timesheets`: `employee_id`, `week_start`, `status`, `submitted_at`, `approved_by_id`, `approved_at`, `total_hours`, `billable_hours`.
- `project_timesheet_entries`: `timesheet_id`, `time_entry_id`; unique mapping prevents duplicate approval.
- `project_expenses`: `project_id`, `work_item_id`, `employee_id`, `category`, `amount`, `currency`, `tax_amount`, `receipt_document_id`, `reimbursable`, `billable`, `status`, `invoice_link_id`.
- `project_cost_entries`: `project_id`, `work_item_id`, `cost_type` (`labour`, `expense`, `material`, `subcontract`, `overhead`), `amount`, `currency`, `source`, `reference_id`, `posted_at`.
- `project_billing_runs`: `project_id`, `period`, `currency`, `billing_type`, `gross_amount`, `tax_amount`, `status`, `finance_invoice_id`, `approved_by_id`, `posted_at`, `idempotency_key`.
- `project_billing_lines`: `billing_run_id`, `source_type` (`time`, `expense`, `milestone`, `fixed_fee`), `source_id`, `description`, `quantity`, `rate`, `amount`, `tax_code`, `status`.
- `project_invoice_links`: `finance_invoice_id`, `project_id`, `billing_run_id`, `amount`, `status`, `paid_at`.
- `project_budgets`: `project_id`, `version`, `budget_hours`, `budget_cost`, `budget_revenue`, `currency`, `effective_from`, `approved_by_id`, `status`.
- `project_budget_revisions`: `budget_id`, `reason`, `change_json`, `approved_by_id`, `status`.

#### Resources and capacity

- `project_resource_roles`: `code`, `name`, `default_cost_rate`, `default_billable_rate`, `currency`, `status`.
- `project_employee_skills`: `employee_id`, `skill_code`, `proficiency`, `evidence_document_id`, `verified_by_id`, `status`.
- `project_capacity_calendars`: `employee_id`, `week_start`, `capacity_hours`, `planned_leave_hours`, `holiday_hours`, `source` (`hr`, `manual`), `status`.
- `project_resource_bookings`: `project_id`, `work_item_id`, `employee_id`, `role_code`, `start_date`, `end_date`, `hours_per_day`, `allocation_percent`, `status`, `requested_by_id`, `approved_by_id`.
- `project_workload_snapshots`: `employee_id`, `week_start`, `booked_hours`, `available_hours`, `utilization_percent`, `overallocated`, `status`.

#### Governance, collaboration, automation

- `project_risks`: `project_id`, `title`, `description`, `probability`, `impact`, `score`, `owner_employee_id`, `response_strategy`, `mitigation_plan`, `status`, `due_date`.
- `project_issues`: `project_id`, `work_item_id`, `title`, `description`, `severity`, `status`, `owner_employee_id`, `linked_risk_id`, `resolved_at`.
- `project_decisions`: `project_id`, `title`, `context`, `decision`, `decided_by_id`, `decided_at`, `status`.
- `project_status_updates`: `project_id`, `period`, `health`, `summary`, `achievements`, `blockers`, `next_steps`, `author_employee_id`, `status`, `published_at`.
- `project_goals`: `portfolio_id`, `program_id`, `project_id`, `title`, `metric`, `target`, `current`, `owner_employee_id`, `status`.
- `project_retrospectives`: `project_id`, `sprint_id`, `what_went_well`, `what_did_not`, `actions_json`, `status`, `facilitator_id`.
- `project_comments`: `entity_type`, `entity_id`, `author_id`, `body`, `mentions_json`, `parent_comment_id`, `status`.
- `project_activities`: `entity_type`, `entity_id`, `actor_id`, `action`, `changes_json`, `correlation_id`, `created_at`; append-only.
- `project_attachments`: `entity_type`, `entity_id`, `document_id`, `title`, `status`; Documents owns file bytes.
- `project_automation_rules`: `project_id`, `trigger_json`, `conditions_json`, `actions_json`, `owner_id`, `status`, `run_count`.
- `project_automation_runs`: `rule_id`, `trigger_entity`, `trigger_id`, `status`, `error`, `started_at`, `finished_at`.
- `project_integrations`: `provider` (`jira`, `microsoft_project`, `github`, `gitlab`, `calendar`, `email`), `external_id`, `config_json`, `status`, `last_sync_at`.
- `project_import_batches`: `provider`, `file_document_id`, `status`, `rows_total`, `rows_imported`, `rows_failed`, `error_report_document_id`.
- `project_ai_signals`: `entity_type`, `entity_id`, `signal_type`, `score`, `features_json`, `explanation`, `model_version`, `generated_at`, `review_status`, `reviewed_by_id`.
- `project_ai_actions`: `action_type`, `entity_type`, `entity_id`, `proposed_json`, `status`, `requested_by_id`, `approved_by_id`, `executed_at`, `reversal_reference`.

### 3.5 Cross-module identity rule

- `users.id` is a login identity.
- `hr_employees.id` is the person/resource identity.
- Projects assigns work and bookings to `hr_employees.id`; it resolves `employee.user_id` for notifications and permissions.
- HR plan adds the employee/user link at `docs/modules/08a-HR-IMPLEMENTATION-PLAN.md:184`; Projects depends on that migration.
- If an employee has no user (contractor/vendor), Projects can still book capacity but cannot grant portal access until Identity creates a restricted user.

---

## 4. State machines

Every transition writes `AuditLog` and `project_activities`, emits an outbox event where another module cares, and is guarded by a named predicate covered by tests.

### 4.1 Project

```
draft        --submit-->        approval_pending | customer, budget, dates valid          | audit, approval request
approval_pending--approve-->    approved         | approver limit >= budget/cost          | audit
approval_pending--reject-->     rejected         | reason present                         | audit
approved     --activate-->      active           | resources and milestones configured    | audit, project.started
active       --hold-->          on_hold          | reason present                         | audit, notifications
on_hold      --resume-->        active           | reason resolved                        | audit
active       --complete-->      completed        | work items closed/waived, unbilled resolved | audit, project.completed, resource release
active       --cancel-->        cancelled        | no unbilled approved time, manager approval | audit, reversals if any
completed    --reopen-->        active           | change request approved                | audit
rejected/cancelled--terminal--> same             | terminal                               | none
```

### 4.2 Work item

```
backlog      --refine-->        todo             | acceptance criteria present            | audit
todo         --start-->         in_progress      | assignee active, capacity checked      | audit, work_item.started
in_progress  --block-->         blocked          | blocked_reason and blocker link        | audit, task.overdue risk
blocked      --unblock-->       in_progress      | blocker resolved                       | audit
in_progress  --submit_review--> in_review        | definition of done checklist complete  | audit
in_review    --approve-->       done             | reviewer not assignee unless waived    | audit, completed_at, event
in_review    --request_change--> in_progress     | review comments present                | audit
done         --accept-->        accepted         | customer/PO acceptance if required     | audit, milestone check
accepted     --close-->         closed           | billing state resolved                 | audit
any open     --cancel-->        cancelled        | reason and approval                    | audit
closed/cancelled--reopen-->     in_progress      | reopen reason, version increment       | audit
```

Workflow schemes may rename status labels, but every status maps to a canonical category (`todo`, `active`, `done`, `cancelled`) for reporting.

### 4.3 Sprint/cycle

```
planned      --start-->         active           | dates valid, capacity computed         | audit, sprint.started
active       --complete-->      completed        | unfinished items moved intentionally   | audit, velocity snapshot
active       --cancel-->        cancelled        | approval and reassignment plan         | audit
completed    --terminal-->      completed        | terminal                               | none
```

### 4.4 Milestone

```
planned      --reach-->         reached          | acceptance criteria evidence attached  | audit
reached      --accept-->        accepted         | customer/PM acceptor authority         | audit
accepted     --bill-->          billed           | billing run approved, invoice linked   | audit, milestone.billed
billed       --paid-->          paid             | invoice.paid received                  | audit
paid         --terminal-->      paid             | terminal                               | none
```

### 4.5 Time entry and timesheet

```
draft        --submit-->        submitted        | hours > 0, date within allowed period  | audit, timesheet rollup
submitted    --approve-->       approved         | approver authority, not self unless delegated | audit, timesheet.approved
submitted    --reject-->        rejected         | reason present                         | audit
approved     --invoice-->       invoiced         | billing run linked, not already invoiced | audit, billing line
invoiced     --paid-->          paid             | finance invoice paid                   | audit
approved     --revert-->        draft            | not invoiced, payroll not finalized    | audit
rejected     --resubmit-->      submitted        | corrections made                       | audit
```

### 4.6 Billing run

```
draft        --generate-->      review           | sources approved, no duplicate source IDs | audit, lines computed
review       --approve-->       approved         | totals, tax, and customer valid         | audit
approved     --post-->          invoiced         | Finance invoice id returned, idempotency key | audit, invoice linkage
invoiced     --fail-->          failed           | posting error recorded                  | audit, retry allowed
failed       --retry-->         review           | error resolved                          | audit
invoiced     --terminal-->      invoiced         | terminal; corrections are credit notes  | none
```

### 4.7 Dependency, risk, issue, change request, booking

```
dependency proposed --confirm--> active | no cycle, valid types | audit
dependency active --resolve--> resolved | successor complete or link no longer needed | audit
dependency active --cancel--> cancelled | reason | audit

risk identified --assess--> analysing | probability/impact set | audit
risk analysing --mitigate--> mitigated | response and owner set | audit, notification
risk mitigated --close--> closed | residual risk accepted | audit
risk analysing --escalate--> escalated | severity threshold | audit, PMO notification

issue open --triage--> triaged | severity/owner set | audit
issue triaged --start--> in_progress | assignee active | audit
issue in_progress --resolve--> resolved | resolution notes | audit
issue resolved --close--> closed | verification | audit
issue resolved --reopen--> in_progress | recurrence evidence | audit

change_request draft --submit--> submitted | impact fields complete | audit
change_request submitted --approve--> approved | approval authority | audit, budget/schedule update
change_request submitted --reject--> rejected | reason | audit
change_request approved --apply--> applied | baseline updated | audit

booking requested --approve--> confirmed | employee capacity available | audit, capacity recompute
booking confirmed --fulfill--> fulfilled | time booked or period passed | audit
booking confirmed --cancel--> cancelled | reason | audit, capacity recompute
```

### 4.8 AI action

```
proposed     --review-->        approved         | human reviewer, scope valid           | audit
proposed     --reject-->        rejected         | reason recorded                       | audit
approved     --execute-->       executed         | workflow action succeeded             | audit, on_behalf_of
executed     --reverse-->       reversed         | reversible action and reason          | audit, reversal reference
executed/failed/rejected/reversed --terminal--> same | terminal                         | none
```

---

## 5. API surface

### 5.1 Existing endpoints to retain

- `GET/POST/PATCH/DELETE /projects/projects`
- `GET/POST/PATCH/DELETE /projects/tasks`
- `GET /projects/projects/{id}/summary` (`backend/app/modules/projects/router.py:62-87`)

Keep compatibility during migration but stop allowing direct edits to `actual_hours`, `billable_rate`, and status through generic PATCH once dedicated endpoints are live.

### 5.2 Target endpoints

#### Core work management

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/projects/portfolios` | CRUD | `projects.portfolio.*` | Portfolio management |
| `/projects/programs` | CRUD | `projects.program.*` | Program management |
| `/projects/projects/{id}/activate` | POST | `projects.project.update` | Lifecycle activate |
| `/projects/projects/{id}/hold` | POST | `projects.project.update` | Hold with reason |
| `/projects/projects/{id}/complete` | POST | `projects.project.update` | Complete with guards |
| `/projects/projects/{id}/cancel` | POST | `projects.project.update` | Cancel with approval |
| `/projects/projects/{id}/health` | PATCH | `projects.project.update` | Health/status update |
| `/projects/work-items` | CRUD | `projects.workitem.*` | Generic work item CRUD |
| `/projects/work-items/{id}/transition` | POST | `projects.workitem.update` | Guarded workflow transition |
| `/projects/work-items/{id}/rank` | PATCH | `projects.workitem.update` | Board/backlog ranking |
| `/projects/work-items/{id}/links` | POST/DELETE | `projects.workitem.update` | Dependency/relation links |
| `/projects/work-items/{id}/comments` | CRUD | `projects.comment.*` | Comments/mentions |
| `/projects/boards/{id}` | GET | `projects.project.read` | Board configuration/data |
| `/projects/boards/{id}/columns` | CRUD | `projects.project.update` | WIP columns |
| `/projects/labels` | CRUD | `projects.project.update` | Labels |
| `/projects/custom-fields` | CRUD | `projects.settings.manage` | Custom field config |
| `/projects/workflows` | CRUD | `projects.settings.manage` | Workflow schemes/transitions |
| `/projects/templates` | CRUD | `projects.settings.manage` | Project/work item templates |

#### Agile planning and schedule

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/projects/projects/{id}/backlog` | GET/PATCH | `projects.project.read` / `projects.workitem.update` | Backlog view/reorder |
| `/projects/sprints` | CRUD | `projects.sprint.*` | Sprint/cycle management |
| `/projects/sprints/{id}/start` | POST | `projects.sprint.update` | Start sprint |
| `/projects/sprints/{id}/complete` | POST | `projects.sprint.update` | Complete and snapshot metrics |
| `/projects/projects/{id}/gantt` | GET | `projects.project.read` | Gantt dataset |
| `/projects/dependencies` | POST/DELETE | `projects.schedule.update` | Dependency management |
| `/projects/projects/{id}/critical-path` | GET | `projects.project.read` | Critical path |
| `/projects/milestones` | CRUD | `projects.milestone.*` | Milestones |
| `/projects/milestones/{id}/accept` | POST | `projects.milestone.update` | Acceptance |
| `/projects/baselines` | POST | `projects.schedule.update` | Baseline snapshot |
| `/projects/projects/{id}/schedule-variance` | GET | `projects.project.read` | Baseline vs current |
| `/projects/releases` | CRUD | `projects.release.*` | Releases |

#### Time, cost, billing

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/projects/time-entries` | CRUD | `projects.timeentry.*` | Time entries |
| `/projects/time-entries/{id}/submit` | POST | `projects.timeentry.update` | Submit |
| `/projects/time-entries/{id}/approve` | POST | `projects.timeentry.approve` | Approve |
| `/projects/timesheets` | CRUD | `projects.timesheet.*` | Weekly timesheets |
| `/projects/timesheets/{id}/approve` | POST | `projects.timesheet.approve` | Approve timesheet |
| `/projects/expenses` | CRUD | `projects.expense.*` | Project expenses |
| `/projects/projects/{id}/unbilled` | GET | `projects.billing.read` | Unbilled time/expenses/milestones |
| `/projects/billing-runs` | POST | `projects.billing.create` | Create billing run |
| `/projects/billing-runs/{id}/review` | POST | `projects.billing.update` | Review lines |
| `/projects/billing-runs/{id}/approve` | POST | `projects.billing.approve` | Approve |
| `/projects/billing-runs/{id}/post` | POST | `projects.billing.post` | Send invoice proposal to Finance |
| `/projects/projects/{id}/profitability` | GET | `projects.finance.read` | Budget vs cost vs billed |
| `/projects/projects/{id}/costs` | GET | `projects.finance.read` | Cost ledger |

#### Resources, governance, reporting, AI

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/projects/resources/capacity` | GET | `projects.resource.read` | Leave-aware capacity calendar |
| `/projects/resources/workload` | GET | `projects.resource.read` | Workload heatmap |
| `/projects/resource-bookings` | CRUD | `projects.resource.*` | Bookings |
| `/projects/risks` | CRUD | `projects.risk.*` | Risk register |
| `/projects/issues` | CRUD | `projects.issue.*` | Issue register |
| `/projects/decisions` | CRUD | `projects.governance.*` | Decision log |
| `/projects/change-requests` | CRUD | `projects.change.*` | Scope/cost/schedule changes |
| `/projects/status-updates` | CRUD | `projects.status.*` | Health/status reporting |
| `/projects/goals` | CRUD | `projects.goal.*` | Goals/OKRs |
| `/projects/reports/{key}` | GET | `projects.report.read` | Named reports |
| `/projects/ai/signals` | GET | `projects.ai.read` | AI signals |
| `/projects/ai/actions` | CRUD | `projects.ai.*` | AI proposals/approvals |
| `/projects/automation/rules` | CRUD | `projects.automation.*` | Automation rules |
| `/projects/imports` | POST | `projects.settings.manage` | Jira/MS Project/CSV import |

### 5.3 API conventions

- Pagination/filtering/sorting reuse the shared CRUD helpers (`backend/app/core/crud.py:79-117`).
- Errors reuse `AppError` taxonomy (`backend/app/core/exceptions.py:10-43,53-79`): `409` for illegal transitions/duplicates, `422` for validation failure, `403` for field/permission denial.
- Every POST/PATCH accepts `Idempotency-Key`; billing, time approval, dependency changes, HR booking, and AI actions must be idempotent.
- Document-like responses include `number`, `status`, `version`, and correlation ID.
- Query language: support a constrained `JQL-like` filter DSL mapped to allow-listed ORM fields; no raw SQL from users or AI.

---

## 6. Business rules

- **PJ-01** — `actual_hours` is derived from approved `project_time_entries`; direct edits are rejected once time entries are enabled.
- **PJ-02** — Only `approved` time entries may enter a billing run; submitted, rejected, or invoiced entries are excluded.
- **PJ-03** — A time entry, expense, or milestone can be billed at most once; `invoice_link_id`/billing-line uniqueness prevents double-billing.
- **PJ-04** — Billing type controls billing source: `time_and_material` uses approved time/expenses, `fixed` and `milestone` use accepted milestones, `non_billable`/`internal` never produce customer invoices.
- **PJ-05** — Projects never write Finance tables. A billing run sends a structured invoice proposal to Finance; Finance creates the invoice and journal idempotently (`backend/app/modules/finance/service.py:234-289`).
- **PJ-06** — Project profitability = billed revenue − labour cost − expenses − material/subcontract/overhead cost; unrealised approved time is reported as WIP, not revenue.
- **PJ-07** — Work item assignees and project managers resolve to `hr_employees.id`; `users.id` is used only for login/notification mapping.
- **PJ-08** — Capacity uses HR leave balances/leave requests (`docs/modules/08a-HR-IMPLEMENTATION-PLAN.md:159-160`), attendance summaries (`:123-125`), employment type, and declared weekly hours; bookings cannot exceed available capacity unless explicitly overridden.
- **PJ-09** — Cost rate is derived from HR salary structure (`docs/modules/08a-HR-IMPLEMENTATION-PLAN.md:150`) and role rate; billable rate comes from the project contract/rate card, not from the employee's salary.
- **PJ-10** — Salary, cost rate, billable rate, margin, and payroll-linked fields are field-level restricted (D4) to PMO, Finance, and explicitly authorised managers.
- **PJ-11** — A project cannot complete with open blocking work items, unaccepted critical milestones, or approved unbilled time unless a waiver is approved and audited.
- **PJ-12** — A work item may not be set to `done` by its own assignee when review is required; a reviewer approval is mandatory.
- **PJ-13** — Subtasks cannot be marked done before required child subtasks unless policy allows partial completion.
- **PJ-14** — Dependencies cannot form cycles; lead/lag is stored in days and applied through a deterministic scheduling service.
- **PJ-15** — A completed sprint is immutable; unfinished work must be explicitly moved to another sprint/backlog.
- **PJ-16** — Kanban WIP limits are advisory by default and blocking only when `wip_enforced=true`; violations are visible and audited.
- **PJ-17** — Baselines are immutable; changes require an approved change request.
- **PJ-18** — Risks with probability × impact above threshold create escalation tasks and PMO notifications.
- **PJ-19** — AI may propose transition, assignee, estimate, risk level, status report, billing draft, or notification; a human must approve any write action.
- **PJ-20** — AI cannot approve timesheets, close work items, post invoices, alter statutory/HR data, or change another employee's access.
- **PJ-21** — Every AI signal exposes top three features, model version, generated time, and review state; protected attributes are never inputs.
- **PJ-22** — AI retrieval is permission-scoped; an AI action cannot reveal salary, cost rate, or cross-tenant data to a user who cannot read it directly.
- **PJ-23** — External notifications reuse Integrations and require opt-in for WhatsApp; email uses the provider abstraction; message IDs are stored on `project_activities`.
- **PJ-24** — Attachments are stored in Documents; Projects stores only `document_id` relationships and never duplicates file bytes.
- **PJ-25** — Automation rules execute within the acting user's permissions; if the actor loses permission, the rule pauses and audits.
- **PJ-26** — Every state transition, rate change, budget revision, approval, billing post, AI action, and integration sync writes an audit row.
- **PJ-27** — Imported Jira/MS Project data lands in staging; no import may overwrite approved time entries, invoices, or audited status transitions.
- **PJ-28** — Retention: project financial/timesheet records 8 years, audit/activity 8 years, comments/attachments per Documents policy, AI explanation logs 2 years, closed import batches 2 years.

---

## 7. Workflows (end-to-end)

### 7.1 Project intake to kickoff

1. Customer/internal requester submits intake form with objective, budget range, dates, and sponsor.
2. AI drafts clarification questions and estimate range; PMO reviews.
3. Approval workflow checks budget authority, customer credit, and resource feasibility.
4. Approved intake creates project from template with phases, default work items, milestones, workflow scheme, and roles.
5. Resource bookings are requested; employee leave/capacity from HR is checked.
6. Kickoff publishes project.started event, creates welcome notification, and opens the project workspace.

### 7.2 Agile delivery

1. Product owner refines backlog; work items have acceptance criteria, estimate, priority, and business value.
2. Sprint planning selects items up to capacity; sprint.started emits event.
3. Daily board use: todo → in_progress → blocked/in_review → done; WIP limits and blockers visible.
4. Time is logged against work items; timesheets are submitted weekly and approved by manager.
5. Sprint completion snapshots velocity, cycle time, throughput, carryover, and unplanned work.
6. Retrospective actions become work items and are tracked to closure.

### 7.3 Predictive schedule / Gantt

1. Planner creates milestones, phases, work items, durations, and dependencies.
2. Scheduling service computes start/end dates using dependency types and lead/lag.
3. Critical path is calculated; baseline is approved and snapshotted.
4. Actual progress updates from work items/time entries feed schedule variance.
5. Delays trigger risk signals and notifications; change requests handle baseline changes.

### 7.4 Timesheet to invoice

1. Employee/contractor logs time from web or mobile; punches/timers create draft entries.
2. Weekly timesheet is submitted; manager approves with authority check.
3. Approved billable time, expenses, and accepted milestones become unbilled report rows.
4. Billing run generates lines, applies tax codes, and requests Finance invoice creation.
5. Finance posts invoice/journal idempotently; Projects stores links and marks sources invoiced.
6. `invoice.paid` updates project cash collection, WIP, and profitability.

### 7.5 Resource capacity with HR

1. HR plan publishes employee onboarding/exit and leave ledger changes (`docs/modules/08a-HR-IMPLEMENTATION-PLAN.md:201-205,605-606`).
2. Projects consumes `employee.onboarded` to create a resource record placeholder; no new employee master.
3. Capacity calendar combines employment type, declared hours, approved leave, holidays, and existing bookings.
4. Workload heatmap shows over/under allocation by week.
5. Manager requests booking; AI may suggest an assignee based on skills, availability, and historical velocity, but human confirms.
6. Approved bookings reserve capacity; timesheet actuals reconcile against bookings.

### 7.6 Risk and issue escalation

1. Risk is identified with probability, impact, owner, and response.
2. AI signal scans schedule slips, blocked items, budget variance, and sentiment in status updates.
3. Above threshold, risk escalates to PMO and creates mitigation task.
4. Issue is linked to risk/work item, triaged, resolved, and verified.
5. Decision log records scope/cost/schedule response.

### 7.7 AI-assisted status report

1. AI gathers work item transitions, time entries, risks, milestones, budget variance, and status updates within permission scope.
2. Draft status report includes achievements, blockers, risks, next steps, and health.
3. Project manager reviews/edits and approves publication.
4. Published update is emailed/WhatsApp-sent through Integrations with opt-in and stored as a project artifact.

### 7.8 Support/customer escalation into delivery

1. Support ticket with `needs_project_work` is linked to a project work item by event/subscriber.
2. Work item inherits customer and SLA; due date is set from ticket SLA.
3. Completion notifies Support and optionally the customer.
4. No new customer record is created; CRM/Sales owns customer data.

---

## 8. Accounting / ledger impact

| Event | Debit | Credit | Guard/owner |
|---|---|---|---|
| Time logged | None by default | None | Time is operational until approved/invoiced |
| Timesheet approved | Optional WIP debit | Labour absorbed credit | Only if tenant enables project WIP accounting; Finance owns accounts |
| Expense recorded | Project expense/WIP | AP payable or employee reimbursement | Receipt document and approval present |
| Billing run posted | AR debit | Revenue credit | Finance creates invoice/journal via `finance/service.py:234-289` |
| Tax on billing | AR debit | Output tax payable | GST rules come from Finance/GST module; Projects stores tax code only |
| Milestone billed | AR debit | Revenue/deferred revenue credit | Milestone accepted and not billed before |
| Customer payment | Bank/Cash debit | AR credit | Finance payment service; Projects updates link on `invoice.paid` |
| Reimbursement | Employee reimbursement payable | Bank | Expense approved, payable not already paid |
| Cost accrual/reversal | Project cost/WIP | Accrual/clearing | Reversal documents only; no deletion |
| Credit note for billing correction | Revenue/Output tax debit | AR credit | Finance owns credit note; Projects links reversal |

Projects never posts directly to `finance_journal_entries`; the Finance service validates periods, account codes, and balance (`backend/app/modules/finance/service.py:55-97,160-231`).

---

## 9. Benchmarks

### 9.1 Benchmark matrix

| Benchmark | Concrete capability observed | What Hertex must match | Hertex differentiator | Not competing / known strength |
|---|---|---|---|---|
| **Jira / Atlassian** | Epic → Story/Task/Bug → Subtask hierarchy; parent/child types are flexible; Scrum/Kanban backlogs; workflow statuses and one-way transitions; approval steps; automation actions (`assign`, `create subtasks`, `create sprints`, `transition`); Rovo/AI search, summaries, suggested tasks, field values, JQL fix, and ticket creation from chat | Work hierarchy, boards/backlogs, custom workflows, approvals, automation, AI assist | ERP-native cost, billing, HR capacity, and Finance ledger in one DB | Jira ecosystem/marketplace and Atlassian's deep issue workflow configuration. Sources: `https://support.atlassian.com/jira-cloud-administration/docs/what-are-issue-types`, `https://support.atlassian.com/jira-software-cloud/docs/use-your-scrum-backlog`, `https://support.atlassian.com/jira-software-cloud/docs/monitor-work-in-a-kanban-project/`, `https://support.atlassian.com/jira-software-cloud/docs/set-up-approval-steps`, `https://support.atlassian.com/cloud-automation/docs/jira-automation-actions/`, `https://support.atlassian.com/organization-administration/docs/understand-atlassian-intelligence-features-in-products` |
| **Linear** | Initiative → Project → Milestone → Issue; Cycles with capacity; structured project updates with health; Insights for cycle time/lead time/flow; triage with AI routing/dedup; agent can create/update issues/projects/milestones/initiatives within permissions; natural-language filters | Fast issue workflow, cycles, health updates, flow metrics, triage, agent scope | Employee-capacity-aware planning and billable/project economics that Linear does not natively cover | Linear's speed, design, and engineering-centric workflow. Sources: `https://linear.app/docs/conceptual-model`, `https://linear.app/docs/use-cycles`, `https://linear.app/docs/project-updates`, `https://linear.app/docs/insights`, `https://linear.app/docs/triage-intelligence`, `https://linear.app/docs/linear-agent`, `https://linear.app/docs/filters` |
| **Asana** | Timeline/Gantt with dependencies, critical path, baseline, auto-shifting; workload across projects; Estimated/Actual time; AI features for summaries, status, goals, projects, rule creation, AI Studio, AI Teammates; admin AI control | Gantt, workload, time tracking, status automation, AI summaries | Timesheet approval→invoice→ledger and HR leave-aware capacity | Asana's Work Graph and cross-tool AI context. Sources: `https://help.asana.com/s/article/timeline`, `https://help.asana.com/s/article/plan-and-execute-projects-with-timeline`, `https://help.asana.com/s/article/managing-tasks-and-dependencies-with-timeline`, `https://help.asana.com/s/article/reporting-with-workload`, `https://help.asana.com/s/article/time-tracking-in-asana`, `https://help.asana.com/s/article/asana-ai-features-and-admin-controls` |
| **Monday.com** | Dependency modes FS/SS/FF/SF and flexible/strict/no-action; Gantt; Workload View; Resource Directory/Planner/Capacity Manager; portfolio Risk Insights scanning boards for daily risk list; AI agents with scoped permissions and action logs; AI governance controls | Dependency modes, workload, resource directory, risk insights, agent governance | Cost/rate/invoice integration with Finance and HR salary/cost data | Monday's no-code board flexibility and dashboards. Sources: `https://support.monday.com/hc/en-us/articles/360014437599-Project-management-with-monday-com`, `https://support.monday.com/hc/en-us/articles/360007402599-Dependencies-on-monday-com`, `https://support.monday.com/hc/en-us/articles/360010166559`, `https://support.monday.com/hc/en-us/articles/23716681570578-Work-Management-for-Enterprise`, `https://support.monday.com/hc/en-us/articles/22551628427666-The-portfolio-Risk-Insights`, `https://support.monday.com/hc/en-us/articles/33347027353746-AI-Agents-on-monday-com`, `https://support.monday.com/hc/en-us/articles/30934592475410-AI-Permissions-and-Governance` |
| **ClickUp** | Space → Folder → List → task; Gantt with cascade rescheduling/critical path; Workload by tasks/time/points/custom fields and capacity; timesheets with submit/review/approve; billable reports; Brain/agents with task/doc tools and role/model/spend controls | Hierarchy, Gantt, workload by multiple measures, timesheet approvals, billable reports, AI tool controls | Native ERP billing and cost ledger, not just billable reports | ClickUp's all-in-one breadth and Brain memory/MCP ecosystem. Sources: `https://help.clickup.com/hc/en-us/articles/13856392825367-The-Hierarchy-overview`, `https://help.clickup.com/hc/en-us/articles/40982447293207-How-to-use-Gantt-charts-for-project-planning`, `https://help.clickup.com/hc/en-us/articles/6310449699735-Use-Workload-view`, `https://help.clickup.com/hc/en-us/articles/21302696626967-Timesheets-Hub`, `https://help.clickup.com/hc/en-us/articles/12578085238039-What-is-ClickUp-Brain-AI`, `https://help.clickup.com/hc/en-us/articles/44785311467671-Manage-ClickUp-AI-access-for-roles-and-people` |
| **Microsoft Planner/Project** | Plans with Grid/Board/Schedule/Charts; Timeline/Gantt, dependencies, sprints, workload, goals, portfolios; Project desktop has resource leveling, costing/budgeting, critical path; Planner Agent generates tasks/status reports and never marks tasks complete automatically | Board/schedule/dependencies/goals, status reports, human-complete rule | Single system for delivery, payroll-cost capacity, customer billing, and Indian compliance | Microsoft 365 grounding and enterprise reporting. Sources: `https://learn.microsoft.com/en-us/planner/planner-for-admins`, `https://learn.microsoft.com/en-us/office365/servicedescriptions/project-online-service-description/project-web-service-description`, `https://support.microsoft.com/en-us/planner/copilot/access-planner-agent`, `https://support.microsoft.com/en-us/planner/copilot/generate-automatic-status-reports-with-planner-agent`, `https://support.microsoft.com/en-us/planner/copilot/execute-tasks-with-planner-agent` |
| **Smartsheet** | Dependency-driven Gantt with predecessor/duration/% complete; workload heatmap and capacity view; itemized time, expense categories, time approvals and locked entries; multistep approval workflows; portfolio reports; AI/MCP assistant with tool approval/block controls | Dependency scheduling, capacity, time approvals, approvals, portfolio reports, AI permissions | Native invoice posting and HR-linked resource economics | Smartsheet's spreadsheet familiarity and workflow maturity. Sources: `http://help.smartsheet.com/learning-track/project-setup-gantt-view/configure-dependencies`, `https://help.smartsheet.com/articles/2483101-workload-tracking-in-smartsheet`, `https://help.smartsheet.com/articles/2480851-track-time-in-resource-management`, `https://help.smartsheet.com/articles/2479276-request-approval-from-stakeholders`, `https://help.smartsheet.com/articles/2483721-conversational-ai-smart-assist-and-mcp`, `https://help.smartsheet.com/articles/2483722-ai-management-overview` |
| **PMBOK / Agile guidance** | PMBOK 8th Edition has six principles and seven domains including governance, scope, schedule, finance, stakeholders, resources, risk; Agile Practice Guide 2nd Edition covers flow metrics, outcomes, scaling, AI-enabled delivery, and psychological safety | Governance, finance, resources, risk, flow metrics, tailoring, ethical AI | Operationalises these in one tenant-scoped ERP rather than a methodology doc | PMI's standards authority. Sources: `https://www.pmi.org/pmbok-guide`, `https://www.pmi.org/pmbok-guide-standards/practice-guides/agile`, `https://www.pmi.org/blog/agile-practice-guide-second-edition` |

### 9.2 Source verification status

| Claim | Status | Note |
|---|---|---|
| Vendor capabilities listed above | Verified from official vendor/help pages via research excerpts | Some pages do not expose publication dates; dates are not load-bearing |
| Jira Gantt/critical path, native people-capacity planning, budgets/costs/billing, AI risk prediction | `UNVERIFIED` in this research pass | Not observed; do not claim Jira lacks them in customer-facing material |
| Linear Gantt/dependencies, people capacity, time tracking, budgets/billing, approvals, risk prediction | `UNVERIFIED` in this research pass | Not observed |
| Asana detailed native budget/cost model and explicit risk prediction | `UNVERIFIED` in this research pass | Asana has smart status/blind spots, not confirmed predictive risk |
| Monday generic approval workflow mechanics and timesheet-style approvals | `UNVERIFIED` in this research pass | Permissions/governance and agents were verified |
| ClickUp native budget/cost module, portfolio object model, explicit risk prediction | `UNVERIFIED` in this research pass | Billable time and workload verified |
| Microsoft Planner native budgeting, custom approvals, cross-project resource optimisation | `UNVERIFIED` in this research pass | A non-authoritative Q&A suggested no full budget module; not relied on |
| Smartsheet billing/invoicing | `UNVERIFIED` | Fees/expenses/time categories verified, full billing not |
| PMI product-specific implementation details | Out of scope | PMI provides standards/guidance, not software features |

### 9.3 Parity gap list to close

1. Work-item hierarchy and configurable workflows (Jira/Linear/ClickUp parity).
2. Board/backlog/sprint/cycle with WIP limits and flow metrics (Jira/Linear parity).
3. Gantt, dependencies, critical path, baseline, variance (Asana/Monday/ClickUp/Smartsheet parity).
4. Workload, capacity, skills, resource booking (Asana/Monday/ClickUp/Smartsheet parity).
5. Timesheets, approvals, billable reports, expenses (ClickUp/Smartsheet parity).
6. Portfolio/program/goal/OKR and risk register (PMI/Asana/Monday/Smartsheet parity).
7. AI summaries, reports, triage, routing, agents, and admin governance (all leaders).
8. ERP-native differentiators beyond parity: HR leave-aware capacity, HR cost rates, customer billing into Finance ledger, GST-aware invoicing, Tally import, WhatsApp opt-in updates, and single audit trail.

---

## 10. AI capabilities

### 10.1 Tier 1 — embedded intelligence

| Signal | Decision it changes | Top features | Guardrail |
|---|---|---|---|
| Delay risk | Manager reassigns, de-scopes, or escalates before slip | Actual vs planned hours, remaining work, velocity, dependency slippage, blocked days | Read-only; explanation required |
| Budget overrun risk | PMO reviews budget revision or scope change | Burn rate, committed bookings, approved time cost, expense trend, EAC | Read-only; no budget change |
| Billing leakage | Finance/PM recovers unbilled work | Approved billable hours without billing line, milestone accepted but unbilled, expense unreimbursed | Read-only |
| Resource over-allocation risk | Manager rebalances bookings | HR leave, existing bookings, capacity calendar, sprint load | Suggest only; human approves booking change |
| Duplicate/similar work item | Product owner merges or links | Title/description embedding, labels, linked customer/ticket, reporter | No automatic merge |
| Best assignee suggestion | Manager chooses owner | Skills, capacity, historical throughput, work-item type, current WIP | No auto-assign; no protected attributes |
| Risk signal from activity | PMO opens/escalates risk | Blocked transitions, overdue items, negative status language, critical-path impact | Explainable; human triage |
| Estimate confidence | Team adjusts estimate | Similar past items, estimator history, complexity, defect rate | Read-only; never silently changes estimate |
| Health recommendation | PM sets project health | Schedule variance, budget variance, risk score, blocker count, milestone acceptance | Suggest health only; PM records final health |

Vendor precedents: Monday Risk Insights scans linked boards and produces severity/risk lists; Linear Insights covers cycle time/lead time/burn-up; Asana smart status surfaces blind spots/roadblocks; Microsoft Planner Agent reports risks/blockers; ClickUp Brain can suggest reassignment based on availability.

### 10.2 Tier 2 — conversational read-only "Ask Hertex"

Add project intents to `backend/app/modules/ai/service.py:20-36,92-171`:

- "Which projects are at risk this month?"
- "Show unbilled approved time for project X."
- "What is the critical path for project Y?"
- "Who is over-allocated next week?"
- "Summarize the latest status report for project Z."
- "What changed in the baseline?"
- "Which work items are blocked by customer inputs?"
- "Show cycle time by team for the last three sprints."
- "What can we invoice this week?"

Rules:

- Read-only ORM intents only (A2).
- Permission scoped by tenant, project role, and field-level D4; salary/cost/margin answers are redacted without `projects.finance.read`.
- Every answer cites the underlying project records/report rows.
- No raw SQL, no cross-tenant retrieval, no model-based authorisation (A1).

### 10.3 Tier 3 — agentic actions

All actions are workflow-engine action types (A3), audited with `on_behalf_of`, reversible where applicable, and visible in a review queue.

| Action | Trigger | Approval | Reversal |
|---|---|---|---|
| Draft project from intake/brief | Intake submitted | PMO approval before creation | Archive draft |
| Generate work-item checklist from brief/meeting notes | Human requests | Product owner approves items | Delete draft items before sprint start |
| Draft status report | Weekly or human request | PM approves publication | Mark report superseded |
| Suggest/draft reassignment | Over-allocation signal | Manager and affected employee context reviewed | Revert booking/assignee change |
| Draft risk and mitigation task | Risk signal | Risk owner accepts | Close duplicate risk |
| Draft billing run | Period close | Finance/PM approval before posting | Discard draft billing run |
| Draft WhatsApp/email stakeholder update | Status published | Opt-in and template approval | Send correction, never delete history |
| Triage inbound item | Support/channel event | Human accepts/routes | Reopen and re-route |
| Import mapping suggestion | Jira/MS Project import | PMO approves mapping | Re-run import batch with correction |

Prohibited: auto-close work items, auto-approve time, auto-post invoices, auto-change baselines, auto-book capacity without approval, auto-send without opt-in, auto-deny leave or employee access, or autonomous termination/performance decisions.

### 10.4 AI governance

- A4: top three features and model version on every signal.
- A5: per-tenant token/credit budget; prefer batch tabular models over LLM calls for scoring.
- Permission inheritance: retrieved context and action scope are limited to what the human actor can access; align with Linear, Asana, ClickUp, Monday, and Smartsheet controls.
- Data handling: use providers with no training on customer data and zero/controlled retention where possible; record provider, region, retention commitment, and data categories in Settings.
- Human oversight: Microsoft Planner Agent's rule that the agent never marks tasks complete is adopted as a standing Hertex rule for employment/financial state.
- Logging: store prompt metadata, retrieved record IDs, model/provider, output, approver, executed action, and reversal reference; never store secrets or full sensitive payloads.
- Fairness: no protected attributes in work-item assignment, performance, or capacity signals; monitor distributional effects where legally reviewable and privacy-preserving.
- Governance sources: NIST AI RMF `https://www.nist.gov/itl/ai-risk-management-framework`, EU AI Act transparency/high-risk obligations `https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai`, GDPR Article 22 automated-decision safeguards `https://gdpr-info.eu/art-22-gdpr`, plus vendor governance pages cited in §9.

---

## 11. Non-functional & security

### 11.1 Performance

- Project/task/work-item list p95 < 300 ms at 100k work items.
- Board load p95 < 500 ms for 2,000 items; incremental updates via partial refresh.
- Gantt dataset p95 < 1 s for 5,000 items; asynchronous job above that.
- Timesheet week view p95 < 300 ms; billing run preview for 10,000 lines < 5 s.
- Workload heatmap for 500 employees × 12 weeks < 2 s.
- AI signal batch generation for 10k work items runs nightly, outside request path.
- Reports either complete < 5 s or move to job status with notification.

### 11.2 Concurrency and idempotency

- Optimistic `version` on work items, projects, timesheets, billing runs, bookings, and budgets.
- Row locks on sprint start/complete, timesheet approve, billing post, and baseline creation.
- Unique constraints: project number per tenant, work-item number per tenant/project, one active booking per employee/day/project unless split allowed, one time entry per source/external ID, one billing line per source record.
- All POST/PATCH accepts `Idempotency-Key`; retries return the original result.
- Outbox events carry correlation IDs; subscribers are idempotent.

### 11.3 RBAC and field-level security

Extend `backend/app/core/permissions_catalog.py:25-40` with project extras:

- `projects.portfolio.*`, `projects.program.*`, `projects.workitem.*`, `projects.sprint.*`, `projects.schedule.*`, `projects.milestone.*`, `projects.timeentry.*`, `projects.timesheet.*`, `projects.expense.*`, `projects.billing.*`, `projects.finance.read`, `projects.resource.*`, `projects.risk.*`, `projects.issue.*`, `projects.change.*`, `projects.governance.*`, `projects.goal.*`, `projects.status.*`, `projects.report.read`, `projects.ai.*`, `projects.automation.*`, `projects.settings.manage`, `projects.import.manage`.

Role guidance:

- PMO: full project/workflow/resource/report permissions, no HR payroll writes, no Finance posting unless also Finance.
- Project manager: project/work-item/time approval/booking/risk within assigned projects.
- Team member: work items assigned to them, own time entries, own timesheet, read project docs.
- Finance: billing/finance read/approve/post, rates and margins; no HR statutory writes.
- HR: employee/resource read for capacity, salary/cost masked unless HR+Finance.
- Customer/guest: status/milestone comments only, explicit opt-in, no internal notes/costs.

D4 fields: salary-derived cost rate, billable rate, margin, budget cost, payroll data, employee statutory IDs, and guest-visible comments are masked server-side.

### 11.4 Audit, retention, privacy

- Append-only `project_activities` plus framework `AuditLog` for every transition.
- Immutable baselines, timesheets after approval, billing lines after posting, and AI action records.
- DPDP: employee/customer personal data purpose-limited; retain timesheets/payroll-linked records 8 years; comments/attachments per Documents; AI logs 2 years.
- External AI providers must not train on tenant data; record retention/region commitments; no candidate/employee statutory IDs sent to AI.
- Secrets: Jira/Microsoft/Git/email/webhook tokens encrypted at rest and never returned in API responses.

---

## 12. Reporting & analytics

| Report/KPI | Definition | Materialised view/candidate |
|---|---|---|
| Project health | Composite of schedule variance, budget variance, risk score, blockers, milestone acceptance | `mv_project_health` |
| Budget vs actual | Budget cost/revenue/hours vs actual cost, billed, committed | `mv_project_profitability` |
| EAC/ETC/CPI/SPI | Earned-value style forecast from baseline/planned/actual values | `mv_project_earned_value` |
| Utilisation | Booked/actual hours ÷ available capacity by employee/team/week | `mv_project_utilisation` |
| Workload heatmap | Bookings vs HR-adjusted capacity by week | `mv_project_workload` |
| Unbilled WIP | Approved billable time/expenses/accepted milestones not yet invoiced | `mv_project_unbilled` |
| Billing leakage | Billable work items with no approved time or no billing line | `mv_project_billing_leakage` |
| Velocity | Completed story points by sprint/team | `mv_project_velocity` |
| Cycle/lead time | Work item first-start → done and created → done distributions | `mv_project_flow_metrics` |
| Cumulative flow | Work item counts by status category over time | `mv_project_cumulative_flow` |
| Throughput/rework | Completed items and reopened items by period | `mv_project_throughput` |
| Risk heatmap | Risk probability × impact by project/portfolio | `mv_project_risk_heatmap` |
| Milestone schedule | Planned vs actual acceptance and billing | `mv_project_milestones` |
| Timesheet compliance | Submitted/approved/rejected/late timesheets by team | `mv_timesheet_compliance` |
| Portfolio benefits | Goal/OKR target vs current by portfolio/program | `mv_project_goals` |
| AI review queue | Signals/actions by type, score, review state, reversal | `mv_project_ai_governance` |

Reports must respect row-level tenancy, project permissions, and D4 masking.

---

## 13. Integrations

### 13.1 Internal event contracts

| Event | Direction | Payload | Subscribers |
|---|---|---|---|
| `project.started` | out | project_id, tenant_id, manager_employee_id | Analytics, Integrations, HR onboarding resource alignment |
| `project.completed` | out | project_id, unbilled_amount, resource_ids | HR resource release, Analytics |
| `work_item.transitioned` | out | work_item_id, from, to, actor_id | Analytics, automation, AI signals |
| `work_item.blocked` | out | work_item_id, blocker_id, reason | Notifications, risk worker |
| `sprint.completed` | out | sprint_id, velocity, carryover | Analytics, retrospective worker |
| `timesheet.approved` | out | timesheet_id, employee_id, hours, billable_hours | Payroll cost feed, Analytics, billing eligibility |
| `billing.posted` | out | billing_run_id, finance_invoice_id, amount | Finance reconciliation, Analytics, notifications |
| `milestone.billed` | out | milestone_id, invoice_id, amount | Sales/Finance, Analytics, customer notification |
| `invoice.paid` | in | invoice_id, amount, paid_at | Mark project invoice links paid; update profitability |
| `employee.onboarded` | in | employee_id, user_id | Create project resource placeholder; capacity calendar |
| `employee.exited` | in | employee_id, date_of_exit | Release future bookings; reassign open work items via human workflow |
| `leave.approved` | in | employee_id, dates, hours | Capacity calendar recompute |
| `channel_message.received` | in/out | channel, external_id, module, related_id | Candidate/customer threaded updates via Integrations |
| `project.ai.action.executed` | out | action_id, actor_id, on_behalf_of, reversal_reference | Audit, governance dashboard |

All events route through the transactional outbox; current in-process bus at `backend/app/core/events.py:21-39` is not the production integration path.

### 13.2 External integrations

- **Jira import**: projects, issues, subtasks, status mapping, users→employees mapping, worklogs, attachments metadata; staging first, no overwrite of approved time.
- **Microsoft Project/Planner import**: tasks, durations, dependencies, milestones, resources, baselines; map to Gantt and dependency models.
- **CSV/Excel import**: projects/work items/time entries/expenses with validation report.
- **GitHub/GitLab**: link pull requests/commits to work items by URL or webhook; no writing code systems from Hertex in v1.
- **Calendar**: due dates/milestones/meetings to employee calendar; use tenant calendar settings, no duplicate event master.
- **Email**: adapter for notifications, status reports, invoice/billing notices, and inbound threading.
- **WhatsApp**: reuse `send_message()` and opt-in checks; useful for field updates and customer milestone notices.
- **Documents**: attachments, deliverables, meeting notes, imported files, approval evidence.
- **Identity**: user provisioning for project portal access; no project-local roles stored as users.
- **Finance**: invoice proposals, journal links, payment status, financial periods.
- **HR**: employee/resource identity, leave, attendance, salary structure/cost rate, onboarding/exit.
- **Support/CRM/Sales**: customer and ticket context; no duplicate customer table.
- **Analytics/AI**: KPI feeds, signal generation, Ask Hertex intents.
- **MCP/agent API (later)**: expose a permission-scoped read tool set and narrow action types to approved AI clients, inspired by Linear, Asana, and Smartsheet MCP support; only after governance is green.

### 13.3 Notification policy

- Use `project_automation_rules` for triggers; execute through Integrations and workers.
- Do not send cost/salary/margin to employees or guests unless permission allows.
- WhatsApp requires opt-in with business name and purpose; email honours suppressions/bounces.
- Every notification stores template code, recipient, message ID, consent reference, and correlation ID.

---

## 14. Implementation plan

| Phase | Scope | Acceptance criteria | Effort |
|---|---|---|---|
| **P0 — foundation** | Migration, enums, indexes, numbering, project/work-item extensions, employee link, permissions, D4, audit/activity | Migration up/down; I1/I5/I6 tests; OpenAPI snapshot; no direct edits to derived fields | 6–10 days |
| **P1 — core work management** | Workflow schemes, transitions, boards, backlog, ranking, labels, comments, templates, work-item links | Jira-like work item flow; Playwright board/backlog happy path; guard tests | 10–15 days |
| **P2 — Agile planning** | Sprints/cycles, WIP limits, velocity, flow metrics, triage, sprint immutable completion | Sprint start/complete; metrics snapshot; carryover workflow | 6–10 days |
| **P3 — schedule** | Gantt, four dependency types, lead/lag, cycle detection, critical path, milestones, baselines, variance | Gantt fixture; cycle rejection; critical path correct; baseline immutability | 10–15 days |
| **P4 — time and billing** | Time entries, timesheets, approvals, expenses, unbilled, billing runs, Finance invoice link, profitability | No double-billing; approved-only billing; balanced Finance posting; WIP report | 12–18 days |
| **P5 — HR-integrated resources** | Employee identity mapping, skills, capacity from leave/attendance/salary, bookings, workload heatmap | HR plan integration green; leave-aware capacity; over-allocation alerts; cost rate masking | 10–15 days |
| **P6 — governance** | Portfolios/programs/goals/OKRs, risks/issues/decisions/change requests, intake, status updates | PMBOK domains covered; escalation flow; approvals audited | 10–15 days |
| **P7 — automation and collaboration** | Rules engine runs, webhooks, email/WhatsApp, documents, guest updates, Jira/MS import | Rule idempotency; opt-in enforcement; import dry-run and rollback | 8–12 days |
| **P8 — AI** | Tier 1 signals, Ask Hertex intents, Tier 3 action queue, AI governance reports | A1–A5 verified; human approval; no autonomous destructive actions; feature explanations | 10–15 days |
| **P9 — analytics and rollout** | Materialised views, dashboards, reports, training, cutover, hypercare | Reports tie to ledger/time/HR; one parallel period reconciles; runbook approved | 8–12 days |

Recommended MVP slice: P0–P5 plus minimal P6 risk/status. P7–P9 follow after the core money/people loop is correct. Do not enable billing before P4, HR capacity before P5, or AI writes before P8.

---

## 15. Test plan

### 15.1 Backend unit/invariant tests

- Project and work-item status transition guards; illegal transitions return 409.
- Workflow scheme configuration: status category mapping, required fields, approver rules.
- Work-item hierarchy: parent cannot be subtask, cycles rejected, subtask completion rules.
- Backlog ranking: unique order, reorder stability, sprint move rules.
- Sprint: capacity computation, start/complete guards, immutable completed sprint, carryover.
- Gantt: FS/SS/FF/SF scheduling, lead/lag, cycle detection, critical path on fixture, baseline snapshot/variance.
- Time: derived `actual_hours`, direct edit rejected, duplicate source/external ID no-op, date-window validation.
- Timesheet: submit/approve/reject/resubmit, self-approval denied unless delegated, approved entries locked.
- Billing: approved-only sources, no double-billing, tax code mapping, idempotent Finance call, reversal/credit-note link.
- Profitability: correct revenue/cost/margin/WIP math with fixture data.
- HR: employee mapping, leave-aware capacity, booking conflicts, exited employee future booking release, cost-rate masking.
- Risks/issues/change: score thresholds, escalation task creation, baseline change only via approved request.
- Automation: trigger/condition/action evaluation, permission inheritance, idempotent run, pause on permission loss.
- AI: signals explain top features; intents are read-only; action requires approval; prohibited actions rejected; field masking enforced.
- Tenancy: cross-tenant project/work item/time/billing access returns not found.
- Audit: every transition and sensitive mutation writes audit/activity rows.

### 15.2 Integration tests

- Billing run → Finance invoice → journal → `invoice.paid` → profitability update.
- HR `employee.onboarded` → project resource placeholder → capacity calendar.
- HR `leave.approved` → capacity recompute → over-allocation signal.
- Support ticket → project work item → completion notification.
- WhatsApp/email notification → channel/message record → status update link.
- Jira/MS Project import staging → mapping approval → work items/time entries without overwrite.
- AI action proposal → approval → workflow execution → audit/reversal.

### 15.3 Frontend/Playwright

- Create project → confirm default workflow/template → create work item → board transition → log time → approve timesheet → view profitability.
- Sprint planning → start sprint → complete sprint → velocity/cycle-time view.
- Gantt: add dependency → shift dates → critical path/baseline variance visible.
- Resource: capacity heatmap shows leave-adjusted availability; over-allocation warning and booking approval.
- Billing: unbilled report → billing run → Finance invoice link → paid status.
- Governance: risk escalation, change request, status report approval.
- AI: ask "which projects are at risk?", review a proposed action, approve or reject, verify audit.
- Permission smoke: team member cannot see cost/margin; Finance cannot edit HR payroll; guest sees only approved status.

### 15.4 Quality gates

- `ruff check app`, backend `pytest`, frontend `npm run build`, `alembic check`.
- OpenAPI breaking-change check.
- Performance targets in §11.1 met.
- Conformance row in `docs/PLAN-CONFORMANCE-CHECKLIST.md` updated.

---

## 16. Migration & rollout

### 16.1 Migration sequence

1. Enum/check constraints for existing project/task statuses; map current values (`planning`, `active`, `on_hold`, `completed`, `cancelled`; `todo`, `in_progress`, `done`, `blocked`).
2. Add new columns to `projects` and `project_tasks`; backfill `number`, `version`, `status_category`, `work_item_type`, `currency`.
3. Map `manager_id` and `assignee_id` from `users` to `hr_employees.id` using seeded emails; unresolved records go to a mapping review queue.
4. Create new Projects-owned tables with tenant indexes and FKs.
5. Seed default workflow schemes, board columns, roles/skills, report definitions, and automation templates.
6. Wire `project` sequence from `backend/app/db/seed.py:42` to atomic Settings numbering.
7. Migrate existing `actual_hours` into legacy `project_time_entries` with `source=legacy`, `status=approved`, and `legacy_migrated=true`; preserve original values in an audit snapshot.
8. Import Jira/MS Project/CSV data into staging; dry-run report before commit.
9. Backfill baselines from current planned dates; mark as `legacy_baseline`.

### 16.2 Cutover

- Freeze direct `actual_hours` edits before enabling time entries.
- Start timesheet approvals at a period boundary; never back-bill legacy invoices.
- Enable billing only after Finance validates invoice-line support and GST tax-code mapping.
- Enable resource capacity only after HR employee/user mapping and leave ledger are live.
- Feature flags: `pm.workgraph_v2`, `pm.gantt`, `pm.timesheets`, `pm.billing`, `pm.hr_capacity`, `pm.ai`, `pm.import`.
- Rollback: keep legacy CRUD routes read-only during pilot; reverse Finance documents via credit notes; never delete audited time/approval records.

### 16.3 Data quality gates

- No active project without number, owner employee, currency, billing type, and status.
- No billing run with unapproved or already-invoiced sources.
- No booked hours above capacity unless override approved.
- No AI write action without approver and reversal path.
- No imported record overwrites an audited transition or Finance-linked record.

---

## 17. Risks & open questions

| Risk / question | Impact | Mitigation / owner type |
|---|---|---|
| Scope exceeds Jira feature breadth | delivery slip | Phase gates; MVP P0–P5; named not-competing list; product owner approves scope |
| HR employee/user mapping incomplete | wrong capacity and assignment | Mapping review queue; no auto-assign until resolved; relies on HR plan at `docs/modules/08a-HR-IMPLEMENTATION-PLAN.md:184` |
| Finance invoice-line model missing | cannot bill precisely | Finance adds line/project linkage; Projects sends proposals only; no double-billing |
| Legacy `actual_hours` edits continue | time integrity loss | Freeze field; migration to legacy time entries; audit snapshot |
| Gantt scheduling complexity | incorrect dates | Deterministic scheduler, cycle detection, golden fixtures; no black-box AI scheduling |
| WIP limits too strict for current culture | adoption resistance | Advisory default; enforce per board; manager override audited |
| AI hallucinations in status/billing | wrong decisions | Permission-scoped retrieval, human approval, source citations, no autonomous financial writes |
| AI data leakage to providers | privacy/compliance risk | No-training/ZDR providers, data category allowlist, regional settings, governance log |
| Over-allocation false positives from bad HR leave data | poor resource decisions | HR data quality gates; manual override; explainability |
| Import mapping errors | corrupted work graph | Staging, dry-run, mapping approval, no overwrite of audited records |
| Cost/salary leakage through reports or AI | D4 breach | Server-side masking, report permissions, AI redaction, sensitive-read audit |
| Outbox/workflow engine not durable | missed cross-module updates | P0 verifies outbox; no production enablement on in-process bus |
| Project financials treated as ledger | I3 violation | Finance owns journals; Projects stores links and operational data only |
| Duplicate planning docs under `docs/HERITEX_ERP_AUDIT/modules/` | drift | Treat `docs/modules/` as canonical; add note in README if needed |

---

## 18. Definition of Done

- [x] Alembic migration(s) created, reversible, applied at head `f4e2c8a7b913`; `alembic check` has no PM drift. Caveat: unrelated `finance_approvals`, `finance_vendor_payments`, `procurement_vendor_invoices`, and `sales_order_lines` drift remains outside 09a; a fresh empty-DB replay was not re-executed during finalization.
- [x] Every project/work-item field documented (§3 + `app/modules/projects/schemas.py`); FKs indexed; state guards covered by the 62 passing backend tests.
- [x] I1: no duplicate customer/employee/user/channel tables; cross-module effects use service calls/events.
- [x] I3: billing/posting goes through the Finance invoice service; Projects stores links only and never writes Finance tables directly.
- [x] I4: baselines, approved timesheets, billing lines, and audit/activity records are immutable; corrections use reversals (PM invariant tests).
- [x] I5: every project document has an explicit state machine and named guards (`state_machines.py`, `workflows.py`).
- [x] I6: tenancy, audit, and `on_behalf_of` for AI actions are tested (`test_project_management_integrations.py`, `test_project_management_invariants.py`).
- [x] Jira-class hierarchy, workflows, boards, backlogs, sprints, ranking, labels, comments, and templates are live.
- [x] Gantt, dependency types, lead/lag, critical path, milestones, baselines, and schedule variance are live.
- [x] Time entries, timesheets, approvals, expenses, billing runs, invoice links, and profitability are live with no double-billing.
- [x] HR integration is live: employee assignees, leave-aware capacity, cost-rate masking, onboarding/exit events.
- [x] Portfolios/programs, goals/OKRs, risks/issues/decisions/change requests, intake, and status reports are live.
- [x] Automation, notifications, documents, Jira/MS Project/CSV import, and external links are live and audited.
- [x] Tier 1 signals, Ask Hertex project intents, Tier 3 action queue, feature explanations, and governance reports are live.
- [x] AI cannot auto-close work, approve time, post invoices, change baselines, or expose masked fields (API guards + frontend controls).
- [x] RBAC codes and role templates registered in `permissions_catalog.py`; frontend nav/actions match backend (source-contract tests).
- [x] Events publish through the outbox; project subscriber integration tests are green (HR/support/Finance event tests).
- [x] OpenAPI snapshot generated and checked for breaking changes: `backend/openapi-project-management.json` + `backend/scripts/check_openapi_snapshot.py` (349 distinct PM operations; 5 duplicate POST registrations are shadowed in OpenAPI, additions allowed).
- [x] Idempotency enforced by the shared `Idempotency-Key` middleware and state guards; repeat-call coverage is strongest for billing post, import, outbox, automation, time, and AI actions, while sprint/booking repeats rely on the guards rather than dedicated tests.
- [ ] Playwright happy paths for delivery, Gantt, timesheet-to-invoice, HR capacity, and AI review. Caveat: not met as written — 15 Node built-in smoke/unit/source-contract tests pass instead; no new dependencies (Playwright) were allowed.
- [x] Demo screens exist for board/backlog, Gantt, workload, profitability, and project health.
- [ ] Performance targets met: list p95 < 300 ms at 100k work items; Gantt p95 < 1 s at 5,000 items. Caveat: targets are specified in §11.1 and code/tests, but no large-data benchmark was executed in this environment.
- [x] Runbook covers deployment, rollback, parallel billing, import correction, Finance reconciliation, HR capacity cutover, AI governance, outbox dispatch, and incident checks: `docs/runbooks/project-management.md`.
- [x] `docs/PLAN-CONFORMANCE-CHECKLIST.md` row updated.
