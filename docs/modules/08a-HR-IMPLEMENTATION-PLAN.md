# Hertex ERP — HR Module Implementation Plan

**Status:** planned · **Owner:** backend + frontend + compliance reviewer · **Date:** 2026-11-17
**Scope:** employee lifecycle, attendance/ESSL import, leave, statutory payroll, payslips, compliance reporting, recruitment pipelines, HR integrations, and HR AI.
**Benchmarks:** Zoho People/Payroll/Recruit, SAP SuccessFactors Employee Central/Payroll/Recruiting, Tally + Excel + WhatsApp, Odoo HR/Payroll.
**Normative base:** `docs/modules/00-MASTER-ARCHITECTURE.md`; this plan must not contradict invariants I1–I6, the 13-event catalogue, 52-table ownership, state-machine rules, AI tiers A1–A5, or D2/D3/D4 decisions.

---

## 1. Purpose & scope

### 1.1 Purpose

Own the people-data and payroll correctness spine: one tenant-scoped employee master, immutable attendance facts, leave balances, effective-dated statutory rules, deterministic payroll computation, balanced journals, auditable payslips, and a recruitment pipeline that hands accepted offers to onboarding without duplicating identity or employee records.

The product priority remains **"adequate but statutorily correct"** from `docs/modules/08-HR.md:3-5`: HR is not the visual differentiator; wrong PF/ESI/TDS/PT or a payroll run that never reaches Finance is a compliance liability.

### 1.2 In scope

- Departments, employee master, salary structures, statutory identifiers, employee lifecycle.
- Attendance daily summaries, raw punches, ESSL/biometric import, overtime and exceptions.
- Leave policies, accrual, balances, append-only leave ledger, approval workflow.
- Payroll rules, monthly runs, payslips, employer contributions, professional tax, TDS, journals, payment state.
- PF/ESI/TDS/PT/gratuity/bonus statutory exports and reconciliation.
- Recruitment: requisitions, job postings, candidates, applications, interview stages, offers, offer-to-onboarding handoff.
- Meta/WhatsApp and email notifications with opt-in, AI-assisted HR/recruitment signals, HR analytics.

### 1.3 Out of scope / deliberately deferred

- Full performance-appraisal suite and 360-feedback forms (v2).
- Full shift rostering and labor-cost optimisation UI; v1 stores `shift_code` and computes attendance exceptions only.
- Full HRBP/market-compensation benchmarking data license.
- Autonomous payout, autonomous candidate rejection, or autonomous offer generation; all Tier 3 actions remain human-approved.
- SAML/OIDC/SCIM identity federation; belongs to Identity, not HR.

### 1.4 Relationship to existing docs

`docs/modules/08-HR.md:15` previously marked recruitment ATS, self-service, and rostering as v2. This implementation plan supersedes that scope decision because the user brief explicitly requires recruitment pipelines, Meta/WhatsApp/email, and AI. The statutory priority from `docs/modules/08-HR.md:4-5,37` is unchanged.

---

## 2. Current state (verified from code)

### 2.1 Backend assets that exist

| Area | Current state | Evidence |
|---|---|---|
| API mounting | Backend exposes `/api/v1`; HR router prefix is `/hr` | `backend/app/core/config.py:13`, `backend/app/main.py:60`, `backend/app/api/v1/router.py:7,37`, `backend/app/modules/hr/router.py:46` |
| Model registration | HR models are registered in metadata | `backend/app/db/registry.py:12` |
| ORM tables | `hr_departments`, `hr_employees`, `hr_attendance`, `hr_leave_requests`, `hr_payroll_runs`, `hr_payslips` | `backend/app/modules/hr/models.py:13-17,20-40,43-53,56-71,74-82,85-100` |
| Tenant/audit fields | All six HR models inherit `TenantBaseModel`; tenancy and audit mixins are framework-level | `backend/app/modules/hr/models.py:13,20,43,56,74,85`, `backend/app/db/base.py:16-55` |
| Schemas | CRUD schemas exist for all six resources | `backend/app/modules/hr/schemas.py:11-31,34-88,91-120,123-157,160-181,184-200` |
| Generic CRUD | Departments, employees, attendance, leave requests, payroll runs use generated CRUD router | `backend/app/modules/hr/router.py:49-118`, `backend/app/core/crud.py:156-307` |
| Leave approval | `POST /hr/leave-requests/{id}/approve` sets status/approver and audits | `backend/app/modules/hr/router.py:120-151` |
| Payroll processing | `POST /hr/payroll-runs/{id}/process` generates payslips, updates totals, audits | `backend/app/modules/hr/router.py:154-219` |
| Payslip listing | `GET /hr/payslips` supports pagination and tenant filter | `backend/app/modules/hr/router.py:222-252` |
| Permissions | HR resources and role template exist | `backend/app/core/permissions_catalog.py:17,43-58,65-103`, especially HR role at `:96` |
| Seed data | One department and two employees are seeded; payroll sequence key exists | `backend/app/db/seed.py:33-44,355-363`, sequence materialisation at `:162` |
| Analytics | Dashboard KPI `employee_count` counts active employees | `backend/app/modules/analytics/service.py:141-149,217`, `backend/app/modules/analytics/schemas.py:21` |
| Integration plumbing | `ChannelMessage`, WhatsApp adapter, webhook verification, signature check, send service, and generic notification worker exist | `backend/app/modules/integrations/models.py:12-24`, `backend/app/modules/integrations/service.py:27-101`, `backend/app/modules/integrations/adapters.py:21-39,62-92`, `backend/app/modules/integrations/router.py:35-44,47-55,58-103,139-163`, `backend/app/workers/tasks.py:16-20` |
| AI plumbing | `/ai/ask` and `/ai/insights` exist with read-only intents for non-HR domains | `backend/app/modules/ai/router.py:10-27`, `backend/app/modules/ai/service.py:20-36,92-171,174-227` |

### 2.2 Frontend assets that exist

| Area | Current state | Evidence |
|---|---|---|
| HR pages | Six generic `ResourcePage` wrappers: employees, departments, attendance, leave, payroll, payslips | `frontend/src/pages/resources/hr.jsx:14-56,58-79,81-110,112-166,168-213,215-242` |
| Routes | `/hr/employees`, `/hr/departments`, `/hr/attendance`, `/hr/leave`, `/hr/payroll`, `/hr/payslips` | `frontend/src/App.jsx:44-49,149-154` |
| Sidebar | People group entries are permission-gated | `frontend/src/lib/nav.js:97-106`, `frontend/src/components/AppShell.jsx:38-47`, `frontend/src/store/auth.js:108-113` |
| Generic CRUD | Resource list/create/edit/delete calls are centralised | `frontend/src/components/ResourcePage.jsx:130-163,186-204,251-280` |
| HR actions | Leave approve and payroll process buttons exist | `frontend/src/pages/resources/hr.jsx:115-123,198-206` |
| Payslips | Read-only UI; create/edit/delete disabled | `frontend/src/pages/resources/hr.jsx:215-242`, especially `:223-226` |
| Dashboard | Team size KPI links to employees | `frontend/src/pages/Dashboard.jsx:317-323` |
| Assistant | Starter prompt mentions employees on leave, but no backend intent exists | `frontend/src/pages/Assistant.jsx:21-27` |

### 2.3 Current-state gaps

1. **Payroll is not statutory.** `backend/app/modules/hr/router.py:174-196` computes PF as flat 12% of full salary, ESI as 0.75% only when gross ≤ ₹21,000, and TDS as flat 5% when gross > ₹50,000. There are no ceilings, slabs, employer contributions, professional tax, or regime handling.
2. **No payroll domain service.** Payroll math is inline in the router at `backend/app/modules/hr/router.py:174-196`; there is no `backend/app/modules/hr/service.py`, no engine, no rule snapshot, and no recompute path.
3. **No Finance posting.** `process_payroll` creates payslips and totals only (`backend/app/modules/hr/router.py:184-205`); it publishes no event and posts no journal, violating I3 for money.
4. **No immutability.** Payslips are created through generic CRUD-adjacent code and listed; there is no posted-state guard, version, reversal, or correction document (`backend/app/modules/hr/models.py:85-100`, `backend/app/modules/hr/router.py:222-252`).
5. **Free-form states.** All status fields are `String` with defaults; no Python `Enum`, SQL `CheckConstraint`, or transition table exists in `backend/app/modules/hr/`. This conflicts with I5.
6. **No statutory config.** `08-HR.md:81-84` proposed `hr_pf_esi_tds_rules`; no such model or migration exists.
7. **No leave balances or policy.** Approval only sets `approved`, `approved_by_id`, and `approved_at` (`backend/app/modules/hr/router.py:124-151`); there is no accrual, balance, reject, cancel, carry-forward, or leave ledger.
8. **No attendance computation.** `hr_attendance` stores check-in/check-out/status only (`backend/app/modules/hr/models.py:43-53`); no worked minutes, overtime, raw punches, device source, or ESSL import exists.
9. **No recruitment model/API/UI.** No requisition, candidate, application, interview, offer, pipeline stage, or hiring event exists in code.
10. **No HR events/integrations.** No HR module call to `publish()`, `send_message()`, or `subscribe()` was found; no HR subscriber exists in `backend/app/core/subscribers.py`.
11. **No email provider.** No SMTP/email provider implementation exists; only a generic notification worker seam at `backend/app/workers/tasks.py:16-20`.
12. **No HR AI.** There is no HR intent in `backend/app/modules/ai/service.py:20-36`, although the frontend prompts for leave information at `frontend/src/pages/Assistant.jsx:26`.
13. **No HR tests.** `backend/app/tests/` contains `test_api.py`, `test_finance_flows.py`, `test_integrations.py`, and `conftest.py`; no HR test file or HR API test exists.
14. **No HR migration.** HR tables were created in the initial schema migration `backend/alembic/versions/6a04e2a77f21_initial_schema.py`; no HR-specific migration exists.
15. **Number sequence unused.** `payroll_run` sequence is seeded at `backend/app/db/seed.py:43`, but HR models have no `number` field and CRUD includes no `number_field`/`number_prefix` (`backend/app/modules/hr/models.py:74-82`, `backend/app/modules/hr/router.py:107-118`). This conflicts with D3.
16. **Field-level security absent.** `EmployeeRead` exposes salary directly (`backend/app/modules/hr/schemas.py:73-88`, especially `:84`) with no attribute-level masking; D4 is not implemented for HR.
17. **No separate statutorily significant tables.** PF/ESI/TDS/PT rule versions, compliance reports, challans, tax declarations, and recruitment data have no persistence.

---

## 3. Domain model

### 3.1 Ownership rule

HR owns all `hr_*` tables listed here. It reads `users`, `audit_logs`, `number_sequences`, `finance_accounts`, `finance_journal_entries`, and `channel_messages`; it never writes another module's table directly. Cross-module effects go through service calls, events, and the Finance journal service, preserving I1/I3/I6.

### 3.2 Existing tables to extend

#### `hr_departments` (`backend/app/modules/hr/models.py:13-17`)

- Add `code` unique per tenant, `manager_employee_id` FK to `hr_employees.id`, `cost_center_code` string, `effective_from`, `effective_to`.
- Keep `name`, `description`; retain `is_active` for master soft delete.
- Do not create a duplicated finance cost-centre table in HR; account mapping lives in a tenant setting keyed by `cost_center_code`.

#### `hr_employees` (`backend/app/modules/hr/models.py:20-40`)

- Add `middle_name`, `gender`, `marital_status`, `blood_group`, `nationality`.
- Add statutory identifiers: `pan_number`, `aadhaar_last4`, `uan_number`, `pf_number`, `esic_number`, `pf_eligible`, `esi_eligible`, `pf_state`, `pt_state`, `pt_registration_number`.
- Add lifecycle fields: `confirmation_date`, `notice_period_days`, `date_of_exit`, `exit_reason`, `exit_type`, `rehire_eligible`.
- Replace the single `salary` input path with effective-dated salary structures; keep `salary` as a cached current gross for backward compatibility only.
- Add `tax_regime` enum (`old`, `new`, `not_declared`), `resident_status`, `age_band`, `version` for optimistic locking.
- Store `bank_account`, Aadhaar/PAN, and salary fields encrypted at rest; serializers mask by permission.

#### `hr_attendance` (`backend/app/modules/hr/models.py:43-53`)

- Repurpose as the daily computed summary: `employee_id`, `work_date`, `worked_minutes`, `overtime_minutes`, `late_minutes`, `early_exit_minutes`, `status`, `shift_code`, `source`, `first_punch_at`, `last_punch_at`, `exception_flags`, `version`.
- Unique constraint on `(tenant_id, employee_id, work_date)` for the canonical summary.
- Add `hr_attendance_punches`: `employee_id`, `punch_at`, `punch_type`, `device_id`, `external_id`, `source`, `raw_payload`, `work_date`. Unique `(tenant_id, source, external_id)` makes ESSL retries idempotent.

#### `hr_leave_requests` (`backend/app/modules/hr/models.py:56-71`)

- Add `policy_id`, `is_half_day`, `half_day_part`, `attachment_document_id`, `balance_after`, `rejection_reason`, `cancelled_at`, `version`.
- Keep `employee_id`, `leave_type`, `start_date`, `end_date`, `days`, `reason`, `status`, `approved_by_id`, `approved_at`.
- A leave request is a document, not a balance mutation; balance changes are separate append-only ledger rows.

#### `hr_payroll_runs` (`backend/app/modules/hr/models.py:74-82`)

- Add `number` using Settings numbering, `period`, `rule_set_id`, `cut_off_date`, `attendance_applied`, `employee_count`, `generated_at`, `finalized_at`, `journal_entry_id`, `payment_batch_id`, `locked`, `version`.
- Keep totals; add employer-cost totals and component-level totals.
- Unique `(tenant_id, period)` prevents duplicate runs for one period.

#### `hr_payslips` (`backend/app/modules/hr/models.py:85-100`)

- Add `number`, `rule_snapshot_id`, `salary_structure_snapshot_id`, `payroll_run_id`, `employee_id`, `status`, `currency`, `earnings_json`, `employee_deductions_json`, `employer_contributions_json`, `gross`, `total_employee_deductions`, `net_payable`, `employer_cost`, `paid_at`, `payment_reference`, `replaces_payslip_id`, `version`.
- Keep legacy `pf`, `esi`, `tds`, `other_deductions`, `net` as cached columns for current UI compatibility.
- Posted payslips are immutable; corrections are reversing/replacement payslips (I4).

### 3.3 New HR-owned tables

#### Employee and compensation

- `hr_salary_components`: `code`, `name`, `type` (`earning`, `employee_deduction`, `employer_contribution`), `statutory_flag`, `taxable`, `active`.
- `hr_salary_structures`: `employee_id`, `effective_from`, `effective_to`, `currency`, `component_amounts_json`, `gross_monthly`, `status`, `approved_by_id`.
- `hr_tax_declarations`: `employee_id`, `financial_year`, `regime`, `declaration_json`, `proof_document_ids`, `submitted_at`, `verified_at`, `verified_by_id`, `status`.
- `hr_employee_documents`: `employee_id`, `document_type`, `document_id`, `valid_from`, `valid_to`, `verified_by_id`, `status`; HR owns the relationship, Documents owns the file bytes.

#### Attendance and leave

- `hr_attendance_punches`: as above.
- `hr_attendance_exceptions`: `employee_id`, `work_date`, `exception_type`, `source`, `resolution_status`, `resolved_by_id`, `resolved_at`.
- `hr_leave_policies`: `code`, `leave_type`, `applicable_from`, `locations_json`, `employment_types_json`, `accrual_method`, `accrual_rate`, `max_days`, `carry_forward_limit`, `encashment_allowed`, `include_holidays`, `status`.
- `hr_leave_balances`: `employee_id`, `leave_type`, `financial_year`, `opening`, `accrued`, `used`, `pending`, `adjustment`, `available`, `version`.
- `hr_leave_ledger`: append-only `employee_id`, `leave_type`, `transaction_type` (`opening`, `accrual`, `reservation`, `consumption`, `release`, `adjustment`, `expiry`, `encashment`), `days`, `reference_type`, `reference_id`, `balance_after`.

#### Payroll and statutory rules

- `hr_statutory_rule_sets`: `code`, `financial_year`, `effective_from`, `effective_to`, `state_code`, `status`, `source_urls_json`, `approved_by_id`, `approved_at`.
- `hr_statutory_rules`: `rule_set_id`, `rule_key`, `rule_value_json`, `effective_from`, `effective_to`, `priority`, `notes`. Rule keys include `pf`, `esi`, `pt`, `tds`, `gratuity`, `bonus`, `professional_tax`, `rounding`.
- `hr_payroll_adjustments`: `payroll_run_id`, `employee_id`, `component_code`, `amount`, `reason`, `reference_document_id`, `status`, `approved_by_id`.
- `hr_statutory_challans`: `rule_type`, `period`, `challan_number`, `amount`, `due_date`, `paid_at`, `payment_reference`, `document_id`, `status`.
- `hr_compliance_reports`: `report_type`, `period`, `rule_set_id`, `status`, `generated_at`, `file_document_id`, `submitted_at`, `submitted_by_id`, `acknowledgement_reference`.

#### Recruitment

- `hr_requisitions`: `number`, `department_id`, `role_title`, `headcount`, `job_type`, `location`, `budget_min`, `budget_max`, `hiring_manager_id`, `status`, `approved_by_id`, `approved_at`, `version`.
- `hr_job_postings`: `requisition_id`, `title`, `description`, `channels_json`, `published_at`, `closes_at`, `status`.
- `hr_candidates`: `first_name`, `last_name`, `email`, `phone`, `resume_document_id`, `source`, `consent_status`, `consent_at`, `dpdp_notice_version`, `status`, `owner_id`, `version`.
- `hr_applications`: `candidate_id`, `requisition_id`, `stage_id`, `source`, `applied_at`, `status`, `rating`, `rejection_reason`, `version`.
- `hr_pipeline_stages`: `code`, `name`, `order`, `requisition_id` nullable for global defaults, `sla_hours`, `status`.
- `hr_interviews`: `application_id`, `scheduled_at`, `duration_minutes`, `interviewer_ids`, `mode`, `location_or_link`, `status`, `feedback_json`, `scorecard_json`.
- `hr_offers`: `application_id`, `number`, `salary_json`, `effective_date`, `status`, `sent_at`, `accepted_at`, `declined_at`, `expires_at`, `approved_by_id`, `employee_id`.
- `hr_recruitment_activities`: `candidate_id`, `application_id`, `channel`, `direction`, `template_code`, `message_id`, `sent_at`, `status`, `owner_id`.
- `hr_ai_signals`: `subject_type`, `subject_id`, `signal_type`, `score`, `features_json`, `explanation`, `model_version`, `generated_at`, `review_status`, `reviewed_by_id`.

### 3.4 Cross-module links and constraints

- `hr_employees.user_id` nullable FK to `users.id`: one user per employee, created by Identity on `offer.accepted`; never duplicate user rows in HR.
- Finance owns accounts and journals; HR stores `journal_entry_id` only after the Finance journal service returns it.
- Documents owns file bytes; HR stores document relationships and IDs.
- Integrations owns `channel_messages`; HR creates outbound notification requests and stores only message IDs on HR records.
- All HR tables include tenant-scoped indexes; all transactional tables include `status`, `number` where document-like, `version`, and audit rows on transition.
- Use `Numeric(14,2)` for money, `Numeric(6,2)` for day counts, `Numeric(14,3)` for hours/minutes-derived quantities; store `currency` on salary structures, payroll runs, payslips, and offers.
- No boolean substitute for lifecycle state (`is_processed`, `is_approved`) may be introduced; I5 requires explicit states.

---

## 4. State machines

All transitions use the master format `state --event--> next_state | guard | side effects`, write an `AuditLog` row, and emit events through the outbox where money, identity, or external messaging changes.

### 4.1 Employee

```
draft        --activate-->      active        | DOJ valid, statutory identifiers present or waived | audit, employee.onboarded
active       --place_on_leave--> on_leave     | approved leave exists                              | audit
on_leave     --return-->         active        | leave end date reached                             | audit
active       --notice-->         notice_period | date_of_exit set, notice_days >= 0                | audit
notice_period--exit-->           exited        | clearance checklist complete, final payroll flag   | audit, employee.exited
exited       --rehire-->          draft         | rehire_eligible true                              | audit
exited       --terminal-->        exited        | terminal                                          | none
```

### 4.2 Attendance day

```
missing      --import_punch-->  punched       | source+external_id unique                  | audit, raw punch append
punched      --reconcile-->      present|late|half_day|absent|leave|holiday | policy evaluated | audit, attendance.reconciled
punched      --exception-->      exception     | missing pair, duplicate, outside shift      | audit, exception row
exception    --resolve-->        present|leave|half_day|absent | resolver has attendance.update | audit
resolved     --recompute-->      resolved      | payslip not finalized                      | recompute summary
```

### 4.3 LeaveRequest

```
draft        --submit-->        pending       | dates valid, days > 0, employee active       | audit, reserve balance
pending      --approve-->       approved      | policy exists, balance available, approver authority | audit, consume balance, leave.approved
pending      --reject-->        rejected      | rejection_reason present                     | audit, release balance
pending      --cancel-->        cancelled     | requester or HR before approval              | audit, release balance
approved     --consume-->       consumed      | attendance/ payroll period applied           | audit, attendance status=leave
approved     --cancel-->        cancelled     | HR override, payroll not finalized           | audit, reverse balance
rejected     --terminal-->      rejected      | terminal                                      | none
cancelled    --terminal-->      cancelled     | terminal                                      | none
consumed     --terminal-->      consumed      | terminal; correction is new request + ledger adjustment | none
```

### 4.4 PayrollRun

```
draft      --generate-->       generating    | no duplicate period, rule set resolved     | audit, snapshot employees/rules/attendance
generating --fail-->           draft         | validation errors recorded                 | audit, delete unposted preview slips
generating --review-->         review        | all payslips computed, totals balanced    | audit
review     --revert-->          draft         | no journal posted                          | audit, delete generated payslips
review     --finalize-->        processed     | all checks green, DB row lock acquired     | audit, post balanced journal, payroll.processed
processed  --pay-->             paid          | payment reference and bank details valid   | audit, payment journal, payslip.paid
processed  --close-->           closed        | remittance reconciliation complete         | audit
closed     --terminal-->        closed        | terminal                                    | none
```

### 4.5 Payslip

```
generated  --review-->         reviewed      | all component totals reconcile              | audit
reviewed   --finalize-->       posted        | run finalized, journal linked               | audit, immutability lock
posted     --pay-->             paid          | valid payment reference                     | audit, payment journal
posted     --void-->            void          | not paid, reason recorded                   | audit, reversal entry
paid       --terminal-->        paid          | terminal                                    | none
void       --terminal-->        void          | terminal                                    | none
```

### 4.6 Recruitment requisition, application, and offer

```
requisition draft       --submit-->       approval_pending | headcount/budget present          | audit
approval_pending        --approve-->      approved         | approver limit >= budget         | audit
approval_pending        --reject-->       rejected         | reason present                   | audit
approved                --publish-->      published        | job posting text valid           | audit, job.posted
published               --close-->        closed           | headcount filled or manual close | audit
published               --on_hold-->      on_hold          | reason present                   | audit

application sourced    --apply-->         applied          | candidate consent present        | audit
applied                 --screen-->       screening        | owner assigned                   | audit
screening               --advance-->      interview        | interviewer available            | audit, interview.scheduled
screening               --reject-->       rejected         | structured reason, human actor    | audit
interview               --offer-->        offer            | scorecard complete, budget OK    | audit
offer                   --decline-->      declined         | reason captured                  | audit
offer                   --expire-->       expired          | expires_at passed                | worker audit
offer                   --accept-->       accepted         | human approval, salary within band| audit, create employee draft, employee.onboarded
accepted                --terminal-->     accepted         | terminal                         | none
```

### 4.7 Compliance report

```
draft      --generate-->       generated     | rule set and period locked           | audit, file produced
generated  --review-->          reviewed      | totals tie to payroll journal        | audit
reviewed   --submit-->          submitted     | external reference recorded          | audit, challan/report update
submitted  --acknowledge-->     acknowledged | acknowledgement document stored       | audit
failed     --retry-->           generated     | failure reason resolved              | audit
acknowledged--terminal-->       acknowledged | terminal                              | none
```

---

## 5. API surface

### 5.1 Existing endpoints to retain/version

- Generic CRUD: `/hr/departments`, `/hr/employees`, `/hr/attendance`, `/hr/leave-requests`, `/hr/payroll-runs` from `backend/app/modules/hr/router.py:54-118`.
- Custom: `POST /hr/leave-requests/{id}/approve` (`backend/app/modules/hr/router.py:124-151`), `POST /hr/payroll-runs/{id}/process` (`backend/app/modules/hr/router.py:154-219`), `GET /hr/payslips` (`backend/app/modules/hr/router.py:222-252`).
- Keep `/process` as a compatibility alias to `generate + review` during rollout, but deprecate it after clients move to the new lifecycle endpoints.

### 5.2 Target endpoints

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/hr/employees/{id}/salary-structures` | GET/POST | `hr.employee.read` / `hr.employee.update` | Effective-dated compensation |
| `/hr/employees/{id}/statutory-ids` | PATCH | `hr.employee.update` | Masked statutory identifier update |
| `/hr/employees/{id}/exit` | POST | `hr.employee.update` | Exit workflow |
| `/hr/attendance/punches` | POST | `hr.attendance.create` | Idempotent manual/device punch |
| `/hr/attendance/import/essl` | POST | `hr.attendance.import` | Pull date range from ESSL adapter |
| `/hr/attendance/exceptions` | GET | `hr.attendance.read` | Missing pair/duplicate/out-of-shift exceptions |
| `/hr/attendance/exceptions/{id}/resolve` | POST | `hr.attendance.update` | Resolve exception |
| `/hr/leave-policies` | CRUD | `hr.leavepolicy.*` | Policy configuration |
| `/hr/leave-balances/{employeeId}` | GET | `hr.employee.read` or self | Per-year accrual/balance |
| `/hr/leave-requests/{id}/reject` | POST | `hr.leaverequest.update` | Reject with reason |
| `/hr/leave-requests/{id}/cancel` | POST | `hr.leaverequest.update` or self | Cancel before approval |
| `/hr/statutory-rule-sets` | CRUD | `hr.statutory.manage` | Effective-dated rule versions |
| `/hr/payroll-runs/{id}/generate` | POST | `hr.payrollrun.update` | Snapshot + compute preview payslips |
| `/hr/payroll-runs/{id}/review` | POST | `hr.payrollrun.update` | Approve computed run |
| `/hr/payroll-runs/{id}/finalize` | POST | `hr.payroll.finalize` | Lock, post journal, publish event |
| `/hr/payroll-runs/{id}/revert` | POST | `hr.payroll.finalize` | Revert only before finalize |
| `/hr/payroll-runs/{id}/pay` | POST | `hr.payroll.pay` | Mark paid / payment journal |
| `/hr/payroll-runs/{id}/variance` | GET | `hr.payroll.read` | Compare with last period |
| `/hr/payslips/{id}` | GET | `hr.payslip.read` or self | Masked payslip view/PDF |
| `/hr/payslips/{id}/pay` | POST | `hr.payroll.pay` | Per-employee payment state |
| `/hr/compliance/{type}/{period}` | GET | `hr.compliance.read` | PF/ESI/TDS/PT/gratuity report |
| `/hr/compliance/{id}/submit` | POST | `hr.compliance.submit` | Record external submission |
| `/hr/recruitment/requisitions` | CRUD | `hr.recruitment.*` | Requisition management |
| `/hr/recruitment/jobs` | CRUD | `hr.recruitment.update` | Job postings/channels |
| `/hr/recruitment/candidates` | CRUD | `hr.recruitment.*` | Candidate master |
| `/hr/recruitment/applications` | CRUD | `hr.recruitment.*` | Pipeline movement |
| `/hr/recruitment/applications/{id}/stage` | POST | `hr.recruitment.update` | Guarded stage transition |
| `/hr/recruitment/interviews` | CRUD | `hr.recruitment.update` | Scheduling and scorecards |
| `/hr/recruitment/offers` | CRUD | `hr.recruitment.update` | Offer draft/approval/accept |
| `/hr/recruitment/offers/{id}/accept` | POST | `hr.recruitment.approve` | Human-approved onboarding handoff |
| `/hr/ai/signals` | GET | `hr.ai.signal.read` | Reviewed HR/recruitment AI signals |

### 5.3 API conventions

- Pagination: `page`, `size`, `sort`, `filters` through the shared `Page` schema and CRUD helpers.
- Errors: reuse `AppError` taxonomy in `backend/app/core/exceptions.py:10-43,53-79`; return `409 Conflict` for illegal state transitions and duplicate periods, `422` for statutory-rule validation failure, `403` for field-level denial.
- All POST endpoints accept `Idempotency-Key`; payroll generate/finalize/pay and ESSL import must be idempotent via DB uniqueness and request-key records.
- All document-like responses include `id`, `number`, `status`, `version`, `created_at`, `updated_at`.
- Salary, bank, PAN, Aadhaar, and candidate contact fields are masked unless the caller has the explicit field permission.

---

## 6. Business rules

Numbered rules are testable and must map to unit/integration tests.

- **BR-HR-01** — Every payroll run resolves exactly one effective statutory rule set for its period, tenant, and employee state. Rule snapshots are immutable and referenced by each payslip.
- **BR-HR-02** — PF employee contribution is 12% of PF-qualifying wages, capped by the effective PF wage ceiling. The current rule set must use ₹25,000 from the EPFO wage-ceiling circular dated 28 Sep 2026; earlier periods use the prior ceiling from an effective-dated row. Source: `https://www.epfo.gov.in/notices/wage-ceiling-circular-28-09-2026/`. `UNVERIFIED`: attached PDF is image-based in this research session; legal review must confirm exact clause text before production use.
- **BR-HR-03** — Employer PF is split into EPF and EPS using config-driven rates; the default EPF+EPS employer amount is 12% of the same capped PF wage, with EPS capped per rule. No hard-coded 3.67%/8.33% in code.
- **BR-HR-04** — ESI employee contribution is 0.75% and employer contribution is 3.25% of ESI-qualifying wages up to the effective ceiling. An employee with daily average wage up to ₹176 is exempt from the employee share while the employer share continues, per the official ESIC contribution page (`https://esic.gov.in/contribution`). Contributions are due within 15 days of the calendar month end, and contribution periods are 1 Apr–30 Sep and 1 Oct–31 Mar. Exact ceiling/PwD values are effective-dated config and require legal sign-off.
- **BR-HR-05** — TDS is an annualised monthly estimate using declared regime, age band, taxable salary, deductions permitted by that regime, rebate, surcharge, and cess. It is not a flat percentage. Official AY 2026-27 slabs and new-regime rebate are published by the Income Tax Department (`https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1`); new regime is default but old regime selection must be supported.
- **BR-HR-06** — Professional tax is computed from state-specific, effective-dated slabs, capped at ₹2,500 per year under Article 276; no state slab is hardcoded until verified from the official state gazette. Current non-official source: `https://www.fundraksha.com/hr-software/professional-tax-slabs-by-state`; all included state tables are `UNVERIFIED`.
- **BR-HR-07** — Gratuity accrues at 15 days of wages per completed year or part of a year exceeding six months; applicability date and eligibility follow the Labour Code FAQ (`https://www.labour.gov.in/static/uploads/2026/11/da640b1558a315e81e22ce5ac12f463f.pdf`). Wages follow the common definition across labour codes in the same source.
- **BR-HR-08** — Bonus, if enabled for a tenant, uses effective-dated rule configuration with statutory minimum and maximum; exact applicability and rate require legal review before activation.
- **BR-HR-09** — Payroll snapshots employees, salary structures, rule sets, attendance summaries, and approved adjustments at `generate`. Later master-data changes do not affect a generated run.
- **BR-HR-10** — `finalize` requires zero validation errors, balanced component totals, a locked run row, and a balanced journal. It is idempotent: retrying with the same key returns the same result.
- **BR-HR-11** — A finalized payslip is immutable. Corrections create a replacement payslip and reversal/adjusting journal referencing the original.
- **BR-HR-12** — Employee PF/ESI eligibility, state, and exemption flags are evaluated per pay period; an employee missing mandatory identifiers is flagged, not silently skipped.
- **BR-HR-13** — Attendance affects payroll only through an effective attendance policy: full-month salary, worked-days proration, or overtime-only. Payroll never reads raw punches directly; it reads reconciled daily summaries.
- **BR-HR-14** — ESSL imports are idempotent on `(tenant_id, source, external_id)`; re-fetching overlapping date ranges must not duplicate punches.
- **BR-HR-15** — Leave approval reserves/consumes balance in the leave ledger; rejection/cancellation releases pending balance; available balance may not go negative except for explicitly configured unpaid leave.
- **BR-HR-16** — Leave and attendance cannot be backdated into a finalized payroll period; a payroll adjustment document is required.
- **BR-HR-17** — A job requisition must be approved before a public job posting can be published.
- **BR-HR-18** — Candidate data collection requires a DPDP notice and recorded consent version. WhatsApp messaging additionally requires explicit opt-in stating the business name, per Meta's opt-in requirements (`https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in`).
- **BR-HR-19** — AI may rank or flag candidates/employees but may not make the final hire, reject, pay, finalize, or terminate decision. A shortlist that excludes candidates is treated as a selection decision and requires human review and adverse-impact monitoring (`https://www.naacpldf.org/wp-content/uploads/EEOC-TA-on-Title-VII-and-Use-of-Algorithms.pdf`).
- **BR-HR-20** — Every AI signal exposes top three contributing features, model version, and review state; protected attributes are never inputs.
- **BR-HR-21** — `offer.accept` creates an employee draft and Identity onboarding request through events; HR never writes `users` directly.
- **BR-HR-22** — All HR state transitions append `AuditLog` rows with actor, tenant, IP, user agent, before/after values, and `on_behalf_of` when an agent initiated the action.
- **BR-HR-23** — Salary, bank details, PAN, Aadhaar last4, and candidate contact data are field-level restricted (D4); masking is enforced server-side.
- **BR-HR-24** — Financial/payroll documents and audit logs are retained 8 years; channel messages 2 years; rejected candidate data 2 years unless a longer legal hold applies.

---

## 7. Workflows (end-to-end)

### 7.1 Monthly payroll

1. Create `PayrollRun` for `YYYY-MM`; atomic `number_sequences` assigns `PR-YYYYMM-####` per D3. The unused seed key at `backend/app/db/seed.py:43` is wired here.
2. `generate` locks the period, resolves rule set, snapshots active employees and salary structures, reconciles attendance summaries, applies approved adjustments, and computes preview payslips.
3. Run validation: statutory IDs, PF/ESI/PT state config, TDS declarations, negative net, duplicate employee, component reconciliation, and event-outbox availability.
4. HR reviews variance report and exceptions; `review` approves the run.
5. `finalize` acquires a row lock, posts one balanced journal through Finance (`payroll.processed`), marks payslips posted/immutable, and emits compliance-generation tasks.
6. `pay` records bank payment reference and posts the net-payable-to-bank journal (`payslip.paid`).
7. Compliance reports and challan exports are generated; statutory remittances are recorded as separate journals.

### 7.2 ESSL attendance import

1. Store encrypted ESSL AppKey and device endpoint in tenant settings; never log credentials.
2. Worker calls `GET /api/WebAPI/GetAttendanceBetweenDates` with tenant AppKey and date range, following the third-party API document at `https://ampletrails.com/wp-content/uploads/2021/03/AmpleTrails_Api_Document_Essl.pdf`. `UNVERIFIED`: no official eSSL API specification was found.
3. Persist raw punches with `source=essl` and device `external_id`; duplicate fetch is a no-op.
4. Reconcile punches into one daily summary using shift/holiday/leave policy; create exceptions for missing pairs, duplicate punches, or out-of-shift events.
5. HR resolves exceptions; only reconciled summaries are visible to payroll.

### 7.3 Leave request to payroll

1. Employee/manager creates request; policy lookup determines applicability by location, employment type, and date.
2. Submit reserves pending balance in the ledger.
3. Approver checks balance and authority; approve consumes balance and writes attendance `status=leave` for covered dates.
4. Reject/cancel releases reservation; backdating into a finalized period is blocked.
5. Payroll reads the consumed leave ledger and attendance summary through the attendance policy.

### 7.4 Recruitment to onboarding

1. Manager raises requisition; budget/headcount approval publishes job posting to careers page and opted-in channels.
2. Candidate applies via form, WhatsApp, or email; consent and source are recorded.
3. AI ranks duplicate-risk/job-fit only as a Tier 1 signal; human recruiter moves application through screening/interview stages.
4. Interview scorecards are captured; offer approval checks requisition budget and salary band.
5. Candidate accepts offer; `offer.accepted` publishes an event that creates an employee draft and an Identity onboarding request.
6. Employee completes statutory identifiers and bank details before activation.

### 7.5 HR notification

1. HR action creates a notification request with purpose, recipient, template, and consent check.
2. Integrations `send_message()` writes `channel_messages` and calls the WhatsApp adapter only when opt-in is valid; email goes through the new email adapter.
3. Delivery callback updates `channel_messages`; HR records message IDs on the source document.
4. Failed messages retry with backoff; no payslip content is sent without explicit delivery consent.

---

## 8. Accounting / ledger impact

Finance owns `finance_accounts`, `finance_journal_entries`, and `finance_journal_lines`; HR calls the posting service and stores returned IDs. Every posting is balanced and append-only (I3/I4).

| Event | Debit | Credit | Guard |
|---|---|---|---|
| Salary accrual | Salary Expense components: basic, HRA, special, overtime, taxable allowances | PF Employee Payable, ESI Employee Payable, TDS Payable, PT Payable, Other Deductions Payable, Net Salary Payable | Payslip totals reconcile; run in `review` |
| Employer PF EPS portion | Employer PF Expense (EPS component) | EPS Payable | PF eligible and capped amount computed |
| Employer PF EPF portion | Employer PF Expense (EPF component) | EPF Payable | PF eligible and capped amount computed |
| Employer ESI | Employer ESI Expense | ESI Employer Payable | ESI eligible and not exempt |
| Gratuity accrual | Gratuity Expense | Gratuity Payable | Eligibility/effective rule set valid |
| Salary payment | Net Salary Payable | Bank Account | Payment reference present; payslip `posted` |
| PF/ESI/PT/TDS remittance | Respective payable account | Bank Account | Challan reference present |
| TDS deposit | TDS Payable | Bank Account | Challan and period present |
| Payslip correction | Reversal of original lines | Reversal of original lines; new replacement journal | Original not paid and reason present |
| Recruitment/other HR spend | Expense as configured | Bank/AP per existing Finance flow | Non-payroll HR costs do not bypass AP |

Current code posts none of these: `backend/app/modules/hr/router.py:184-205` only writes payslips and run totals.

---

## 9. Benchmarks

### 9.1 Benchmark comparison

| Benchmark | Table stakes we must match | Differentiator we will prove | Deliberately not competing / known strength |
|---|---|---|---|
| **Tally + Excel + WhatsApp** | Salary register, PF/ESI/TDS deductions, challan export, payslip PDF, employee master import from Excel | Single database: payroll posts a balanced journal, payslips are immutable, and salary outflows appear in cash-flow reporting without re-entry; ESSL punches reconcile to payroll | Tally's CA-facing filing ecosystem and Excel's arbitrary ad-hoc modelling |
| **Zoho People + Payroll** | Employee master, attendance, leave policies, payslips, statutory deductions, approval workflow | Single-DB Finance link and tenant-scoped audit; no CRM/Books/People sync gap; rule snapshots make recomputation deterministic | Zoho's mature self-service portal, mobile app polish, appraisal suite, and global payroll breadth. Zoho People leave policies support company/location/business-unit/division applicability, exclusions, restrictions, accrual, and policies keyed to date of joining (`https://help.zoho.com/portal/en/kb/people/administrator-guide/leave/settings/articles/setting-up-leave-policies-in-zoho-people`) |
| **Zoho Recruit** | Requisitions, candidates, pipelines, interview scheduling, email templates, offer workflow | Recruitment events feed onboarding and Identity in one database; consent/opt-in and WhatsApp are first-class; AI signals are explainable and review-gated | Zoho Recruit's large template marketplace and recruitment CRM depth. Zoho Recruit Blueprints support structured stages and actions such as scheduling interviews, sending email, generating offers, and withdrawing offers (`https://help.zoho.com/portal/en/kb/recruit/automation/blueprint/overview/articles/zoho-recruit-blueprint`, `https://help.zoho.com/portal/en/kb/recruit/talent-management/hiring-pipeline/articles/managing-hiring-pipelines`) |
| **SAP SuccessFactors EC / Payroll** | Position/requisition discipline, approval chains, localisation config, holiday calendars, work schedules, time profiles, accrual rules, audit | India-native statutory engine with effective-dated rules and journal integration, delivered without SAP implementation cost | SAP's enterprise payroll breadth, global localisations, and deep position-management model. SAP best practices explicitly call out Position Management and localisation via holiday calendar, work schedule, time profile, eligibility, time types, and accrual rules (`https://help.sap.com/doc/d1089c292bef49ecb67c63966ee7ba72/2505/en-US/Solution_Scope_SAP_Best_Practices_for_SAP_SuccessFactors_Employee_Central.pdf`) |
| **SAP Recruiting** | Requisition-to-onboarding flow, candidate profile, evaluation, interview, offer | Tighter HR-to-Identity-to-Finance handoff and auditable AI governance | SAP's course catalog, assessment ecosystem, and enterprise onboarding breadth (`https://help.sap.com/docs/successfactors-recruiting/sap-best-practices-for-sap-successfactors-recruiting/recruiting-with-integration-to-position-management-and-onboarding`) |
| **Odoo HR/Payroll** | Employee, attendance, leave, payslip, rules | Cleaner statutory config table, deterministic rule snapshots, and stronger ledger invariants | Odoo's community breadth and flexible studio customisation |
| **WhatsApp-first recruiting tools** | Short mobile forms, reminders, human handover, ATS write-back | Consent-aware shared `channel_messages` log linked to candidate and audit | Tools specialised purely in conversational recruiting. Source for pattern: `https://www.hirin.ai/blog/whatsapp-recruitment-chatbot/` |

### 9.2 Research basis and verification status

| Fact | Verification status | Source |
|---|---|---|
| PF employee/employer rate is 12% and employer share splits into EPF/EPS | Verified | `https://www.epfo.gov.in/epf-scheme/` |
| EPFO published "Wage Ceiling Circular 28.09.2026" and "EPFO Wage Ceiling FAQs" | Verified | `https://www.epfo.gov.in/notices/wage-ceiling-circular-28-09-2026/`, `https://www.epfo.gov.in/tender-notices` |
| Wage ceiling enhancement to ₹25,000 | Partially verified; search extract of official circular, image-only PDF not parsed in this session | `https://pmvbry-cdn.epfindia.gov.in/wp-content/uploads/2026/09/Wage-Ceiling-Circular-28.09.2026.pdf` |
| ESI employee 0.75%, employer 3.25%, daily wage exemption behavior | Verified | `https://esic.gov.in/contribution` |
| AY 2026-27 new/old tax slabs, new regime default, ₹60,000 rebate up to ₹12 lakh | Verified | `https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1`, `https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/itr-2/itr-2-faqs` |
| Labour-code common wages definition, wage payment timing, gratuity formula/date | Verified | `https://www.labour.gov.in/static/uploads/2026/11/da640b1558a315e81e22ce5ac12f463f.pdf` |
| Code on Social Security subsumes EPFO/ESIC/Gratuity/Maternity laws | Verified | `https://www.labour.gov.in/static/uploads/2026/02/83978455025732b99b0165def80ab171.pdf?v=20260609051130` |
| WhatsApp opt-in before messaging, business name, legal compliance | Verified | `https://developers.facebook.com/documentation/business-messaging/whatsapp/getting-opt-in` |
| DPDP Rules 2025 notice/consent obligations | Verified | `https://www.meity.gov.in/static/uploads/2025/11/53450e6e5dc0bfa85ebd78686cadad39.pdf` |
| ESSL API endpoint/punch model | Partially verified; third-party integration doc only | `https://ampletrails.com/wp-content/uploads/2021/03/AmpleTrails_Api_Document_Essl.pdf` |
| Professional-tax state slabs | `UNVERIFIED`; non-official source and official state gazettes not fully reviewed | `https://www.fundraksha.com/hr-software/professional-tax-slabs-by-state` |
| Zoho/SAP benchmarking facts | Verified from vendor help/best-practice pages | URLs in §9.1 |
| AI hiring tools can be "selection procedures" with adverse-impact risk | Verified | `https://www.naacpldf.org/wp-content/uploads/EEOC-TA-on-Title-VII-and-Use-of-Algorithms.pdf`, `https://www.shrm.org/in/topics-tools/news/ai-hiring-tools-discrimination-how-to-validate` |

---

## 10. AI capabilities

### 10.1 Tier 1 — embedded intelligence

| Signal | Decision it changes | Features shown | Guardrail |
|---|---|---|---|
| Attrition risk | Manager starts retention conversation | Tenure, leave pattern, overtime trend | Read-only; no protected attributes; `review_status` required |
| Leave anomaly | HR reviews policy abuse | Weekend-adjacent leave frequency, short-notice rate | Read-only; never auto-reject |
| Payroll variance anomaly | HR reviews a run before finalize | Gross delta, component delta, headcount delta, rule-set change | Read-only; cannot finalize payroll |
| Candidate-job fit | Recruiter prioritises review | Skills match, experience band, location fit | Ranking only; human reviews every rejected candidate |
| Duplicate employee/candidate risk | HR/recruiter merges manually | Name/phone/email/PAN similarity | No automatic merge; A1/A2 enforced |

### 10.2 Tier 2 — conversational read-only

Add HR intents to `backend/app/modules/ai/service.py:20-36,92-171`:

- "How many employees are on leave this month?"
- "Show headcount by department and employment type."
- "Which payroll runs are pending finalize?"
- "What is the hiring funnel for this requisition?"
- "Show leave balance for me" with self-scope.

Salary, bank, PAN, Aadhaar, and candidate PII are never returned through natural language unless the caller has the explicit field permission. No raw SQL from the model: use allow-listed ORM query objects (A2).

### 10.3 Tier 3 — agentic action

All Tier 3 actions are workflow-engine action types (A3), audited with the acting user's identity plus `on_behalf_of`, and reversible where possible.

- Draft WhatsApp candidate follow-up after opt-in.
- Draft interview scheduling email with proposed slots.
- Draft ESSL exception-resolution list for HR review.
- Draft payroll variance memo for review.
- Draft compliance-report submission checklist.

Prohibited: auto-pay, auto-finalize, auto-reject candidate, auto-offer, auto-terminate employee, or autonomous statutory-rule activation.

### 10.4 Governance

- A4: every Tier 1 signal exposes top three features and model version.
- A5: per-tenant token budget; tabular signals use batch models, not LLM calls.
- Hiring AI is a selection procedure when used to shortlist or exclude; monitor adverse impact by legally reviewable groups only through privacy-preserving aggregate reporting, never individual protected-attribute inference.
- Human final decision is not enough by itself to remove selection-procedure obligations; keep scorecards, rationale, and review evidence.
- Current code has Anthropic settings at `backend/app/core/config.py:30-31` but no usage; HR AI must go through the shared AI provider abstraction, not a new direct integration.

---

## 11. Non-functional & security

### 11.1 Performance and concurrency

- List endpoints p95 < 300 ms at 100k rows; payroll document read p95 < 500 ms.
- Payroll generation for 500 employees < 5 s; 5,000 employees < 60 s or moves to a job with progress status.
- ESSL import of 100k punches < 60 s in batches of 5,000 using bulk insert with conflict handling.
- `generate` and `finalize` use `SELECT ... FOR UPDATE` on the payroll-run row; payslips and leave balances use `version` optimistic locking.
- Unique constraints enforce one run per period, one daily attendance summary, and one raw punch per source/external ID.
- All POST endpoints accept `Idempotency-Key`; payroll, ESSL import, and notification sends must not double-run.

### 11.2 Security and compliance

- Extend `backend/app/core/permissions_catalog.py:25-40` with HR extras: `hr.attendance.import`, `hr.payroll.generate`, `hr.payroll.finalize`, `hr.payroll.pay`, `hr.compliance.read`, `hr.compliance.submit`, `hr.statutory.manage`, `hr.leavepolicy.*`, `hr.recruitment.read/create/update/delete/approve`, `hr.ai.signal.read`, `hr.payslip.self`.
- Keep the existing HR resource permissions at `backend/app/core/permissions_catalog.py:17`; update role templates at `:65-103` so HR managers get HR codes, Finance gets payroll-read/compliance-read, and employees get self-service read codes only.
- D4 field-level rules: salary, bank account, PAN, Aadhaar last4, statutory IDs, and candidate contact details masked in all serializers and exports.
- Encrypt statutory identifiers, bank details, ESSL AppKey, and AI model tokens at rest; secrets never appear in audit changes (`backend/app/core/audit.py:12-35` already redacts known secret keys and must be extended for HR fields).
- DPDP: notice version, purpose, consent capture/withdrawal, data-principal access/erasure workflow, breach logging; candidate/employee data purpose-limited.
- Meta/WhatsApp: explicit opt-in and business-name disclosure before any message; opt-in state stored with source/time/text and linked to `channel_messages`.
- Audit every transition, rule change, payslip generation/finalize/pay, ESSL import, notification send, AI action, and field-visible sensitive read where practical.
- Row-level tenancy comes from `backend/app/core/crud.py:26-29`; custom HR endpoints must keep the manual tenant checks pattern already used at `backend/app/modules/hr/router.py:135-136,164-165,233-235`.
- Retention: payroll/payslip/statutory reports 8 years; audit 8 years; channel messages 2 years; rejected candidates 2 years; breach/legal hold overrides deletion.

### 11.3 Reliability

- Event publication uses the transactional outbox required by D2/ADR-002; the current in-process bus at `backend/app/core/events.py:21-39` is not durable and must not be the final integration path.
- Outbox subscriber failures retry with exponential backoff and dead-letter visibility.
- Payroll recompute uses the same rule snapshot; if a rule changes after payslip generation, the payslip retains its original snapshot and a variance report flags the change.
- Backups include HR tables and outbox rows; restore test must verify payslip-to-journal linkage.

---

## 12. Reporting & analytics

| Report/KPI | Definition | Audience |
|---|---|---|
| Salary register | Per-employee earnings/deductions/net/employer cost for a run | HR, Finance |
| Payroll variance | Current vs prior run by component, headcount, and rule set | HR, Finance |
| PF/ESI liability register | Employee/employer contributions by period and challan | Finance, compliance |
| TDS register | Monthly TDS, regime, taxable salary, cumulative tax, Form 16/24Q inputs | Finance, compliance |
| Professional tax register | State-wise deductions, due dates, challans | Finance, compliance |
| Gratuity accrual report | Eligible employees, completed years, accrued liability | Finance, HR |
| Leave utilisation | Entitled/used/pending/expired by policy, department, period | HR, managers |
| Attendance exception report | Missing pairs, duplicates, out-of-shift, manual overrides | HR |
| Headcount/attrition | Active employees, joins, exits, attrition rate by department/type | Management |
| Hiring funnel | Applicants → screening → interview → offer → accepted by requisition/source | Hiring managers |
| Time-to-hire / offer acceptance | Median days by requisition, source, interviewer | Recruiting |
| Consent coverage | Employees/candidates with valid WhatsApp/email consent by purpose | Compliance |
| AI review queue | Signals by type, score, review status, adverse-impact aggregate | HR/recruiting governance |

Reports must be generated through the shared report/export registry when available and must not bypass field-level masking.

---

## 13. Integrations

### 13.1 Existing seams to reuse

- `ChannelMessage` and `send_message()` already support external channel state and WhatsApp delivery (`backend/app/modules/integrations/models.py:12-24`, `backend/app/modules/integrations/service.py:46-101`).
- WhatsApp webhook signature verification and inbound handling exist (`backend/app/modules/integrations/router.py:35-103`).
- Generic notification worker seam exists (`backend/app/workers/tasks.py:16-20`).
- Event publishers in other modules show the intended pattern (`backend/app/modules/sales/router.py:211,319-322`, `backend/app/modules/procurement/router.py:233,315`, `backend/app/modules/support/router.py:94`).

### 13.2 Inbound integrations

| Source | Integration | Idempotency/failure handling |
|---|---|---|
| ESSL/biometric device | Pull punches via date range; map to `hr_attendance_punches`; reconcile daily summaries | Unique source/external ID; overlap-safe; raw payload retained |
| WhatsApp inbound | Existing webhook creates `channel_messages`; subscriber maps opt-in candidate replies to `hr_recruitment_activities` | Dedupe by WhatsApp message ID |
| Email inbound | New email adapter creates `channel_messages` and candidate/application activity | Dedupe by provider message ID |
| Excel/CSV import | Employee master, opening leave balances, historical attendance | Import job with validation report and rollback |
| Tally/legacy payroll | Employee and opening statutory IDs/balances via migration path | Staging table + reconcile report |

### 13.3 Outbound integrations

| Event/action | Direction | Target |
|---|---|---|
| `payroll.processed` | out | Finance journal listener, Analytics, compliance worker |
| `payslip.paid` | out | Analytics, notification worker |
| `leave.approved` | out | Attendance reconciliation, employee notification |
| `attendance.imported` | out | Analytics, exception worker |
| `employee.onboarded` | out | Identity user creation, Projects resource placeholder |
| `employee.exited` | out | Identity deactivation workflow, access-review queue |
| `job.posted` | out | Careers page, opted-in channels |
| `candidate.applied` | out | Recruiting owner notification, duplicate-detection worker |
| `interview.scheduled` | out | Email/WhatsApp candidate and interviewer |
| `offer.accepted` | out | Employee draft, Identity onboarding, Analytics |
| `hr.document.ready` | out | Documents/PDF generation, secure delivery |

All events route through the outbox. External messages must pass consent/opt-in checks before delivery.

### 13.4 External API contracts to add

- ESSL adapter: encrypted AppKey, device base URL, endpoint `GetAttendanceBetweenDates`, retry/backoff, timeout, and field mapping.
- Email adapter: provider abstraction, verified from-domain, templates, bounce/complaint handling, and suppression list.
- WhatsApp: reuse Meta adapter; add template management and opt-in verification for HR purposes.
- Bank payment file export: NEFT/RTGS batch with configurable bank format; never store plaintext credentials.
- Statutory portals: PF ECR, ESI, TDS, and PT exports as versioned file layouts; filing itself remains human/compliance-reviewed unless portal APIs are later verified.

---

## 14. Implementation plan

| Phase | Scope | Acceptance criteria | Effort |
|---|---|---|---|
| **P0 — foundation** | HR migration, enums/check constraints, `version`, numbering, new models, permissions, field-security policy, audit coverage | Migration applies from empty DB and rolls back; OpenAPI snapshot; permission/role seed tests; I1/I5/I6 tests | 5–8 days |
| **P1 — statutory engine (release blocker)** | Effective-dated rule sets, PF/ESI/PT/TDS/gratuity/bonus services, golden-master tests, legal review flags | BR-HR-01..08 green; EPFO/ESIC/IT examples reproduced; rule changes do not mutate old payslips | 8–12 days |
| **P2 — payroll correctness (release blocker)** | Generate/review/finalize/pay lifecycle, finance journal, immutability, adjustments, variance report | BR-HR-09..11 green; journal balanced; double-finalize blocked; payslip immutable; parallel-run variance zero | 8–12 days |
| **P3 — attendance and leave** | Raw punches, daily reconciliation, ESSL adapter, exceptions, leave policies/balances/ledger | BR-HR-12..16 green; ESSL duplicate import no-op; leave balance never negative except unpaid; payroll reads summaries only | 8–12 days |
| **P4 — recruitment pipelines** | Requisition → candidate → application → interview → offer → onboarding, stage guards, scorecards | BR-HR-17,21 green; Playwright hiring flow; offer acceptance creates employee draft via event | 8–12 days |
| **P5 — integrations and AI governance** | Email adapter, WhatsApp opt-in/templates, notification requests, HR AI intents/signals, adverse-impact review queue | BR-HR-18..20,22..24 green; no message without consent; AI cannot write payroll/candidate state without approval | 6–10 days |
| **P6 — compliance and analytics** | PF/ESI/TDS/PT reports, challans, Form 16 inputs, statutory registers, HR dashboards | Reports tie to journal/payroll totals; export files versioned; runbook includes reconciliation | 6–10 days |
| **P7 — rollout** | Backfill, parallel payroll, training, feature flags, cutover, hypercare | One full parallel period reconciles to zero with CA/payroll owner; rollback tested | 5–8 days |

Order is strict: P0 → P1 → P2 → P3/P4 → P5 → P6 → P7. P1 and P2 are release blockers. Do not launch a "working payroll" UI before statutory and journal correctness exist.

---

## 15. Test plan

### 15.1 Backend unit tests

- PF: employee at wage below and above effective ceiling; employer split; non-eligible employee; mid-period rule change.
- ESI: employee/employer shares, ceiling, daily-average exemption, employer share continues when employee exempt.
- TDS: old/new regime, all age bands, rebate, surcharge, cess, previous employment TDS, declaration changes, negative net prevention.
- PT: state with no PT, monthly slab, February-specific slab where verified, annual cap, unknown state rejected until config exists.
- Gratuity/bonus: completed years, part-year >6 months, ineligible period, rule version snapshot.
- Payroll: generate/review/finalize/pay/close guards; double-finalize; immutability; replacement payslip; balanced journal.
- Attendance: ESSL duplicate external ID, overlap date fetch, missing punch, out-of-shift exception, leave overlap, backdated finalized period rejection.
- Leave: accrual, proration, carry-forward cap, pending reservation, approval consumption, reject/cancel release, insufficient balance, unpaid override.
- Recruitment: requisition approval before publish, stage guard, interview scorecard required, offer budget check, outcome decline, human-only acceptance.
- RBAC/D4: HR role can payroll; employee cannot see other salary; Finance can read statutory reports; masked fields never leak in API/export.
- Tenancy: cross-tenant employee/leave/payslip/candidate access returns not found.
- Idempotency: duplicate payroll finalize, duplicate ESSL import, duplicate offer accept, duplicate notification request.

### 15.2 Integration tests

- `payroll.processed` through outbox → Finance journal → Analytics.
- `payslip.paid` → notification request → WhatsApp/email adapter with consent.
- `offer.accepted` → employee draft → Identity onboarding request.
- ESSL import worker → raw punches → daily summary → exception → payroll policy.
- Compliance export → challan/register → journal reconciliation.

### 15.3 Frontend/Playwright

- Create department/employee → mark attendance → create/approve leave → generate/review/finalize payroll → view payslip.
- Recruitment: approve requisition → publish job → candidate applies → schedule interview → offer → accept → employee draft appears.
- Permission smoke: employee self-view shows masked payslip and no HR admin actions.
- Failure injection: finalize with missing statutory ID, leave with insufficient balance, ESSL duplicate import, WhatsApp message without opt-in.

### 15.4 Performance and quality gates

- 100k-row attendance list p95 < 300 ms; 500-employee payroll < 5 s.
- `alembic check` no drift; migration up/down from empty DB.
- `ruff check app`, backend `pytest`, frontend `npm run build` all pass.
- OpenAPI breaking-change check after each phase.
- Conformance row updated in `docs/PLAN-CONFORMANCE-CHECKLIST.md`.

---

## 16. Migration & rollout

### 16.1 Migration sequence

1. Enum/check-constraint migration for existing HR status strings; map known values and quarantine unknowns.
2. Add `version`, `number`, and new columns to existing HR tables; backfill defaults.
3. Create statutory, leave, attendance, recruitment, compliance, and AI signal tables; all with tenant indexes.
4. Wire `payroll_run` sequence from `backend/app/db/seed.py:43` to atomic `next_number()` from Settings (`backend/app/modules/settings/models.py:19-26`, `backend/app/modules/settings/router.py:55-74`).
5. Seed default salary components, leave types, pipeline stages, and statutory rule sets with `status=draft` until legal approval.
6. Backfill open leave balances from any legacy spreadsheet; create opening ledger rows.
7. Import employees from Tally/Excel into staging; validate PAN/UAN/PF/ESI duplicates before commit.

### 16.2 Cutover

- Run our engine in parallel with the existing CA/payroll process for one full month.
- Reconcile gross, each statutory component, employer cost, net pay, and journal totals to zero variance.
- Enable ESSL import in read-only mode first; compare reconciled summaries with manual attendance for two weeks.
- Enable recruitment pipelines before payroll cutover if desired; they do not block statutory correctness.
- Use feature flags: `hr.statutory_v2`, `hr.payroll_journal`, `hr.essl_import`, `hr.recruitment`, `hr.ai_signals`.
- Rollback: keep v1 `/process` endpoint behind flag until one successful parallel payroll; reverse new journals via Finance reversal documents, never by deleting entries.

### 16.3 Data quality gates

- No active employee without employee code, DOJ, salary structure, and statutory-state determination.
- No payroll finalize with unresolved validation errors.
- No WhatsApp/email delivery without consent/opt-in.
- No AI shortlist action without review status and human actor.
- No statutory rule set active without source URL, effective dates, and compliance reviewer.

---

## 17. Risks & open questions

| Risk / question | Impact | Mitigation / owner type |
|---|---|---|
| EPFO wage-ceiling PDF text not machine-parsed in this session | Wrong PF ceiling if copied from stale ₹15,000 doc | Compliance reviewer verifies official gazette/circular text; implementation uses effective-dated rule row; do not activate until sign-off |
| State professional-tax slabs not fully verified from official gazettes | wrong PT deductions | Ship unknown-state rejection; legal/compliance reviewer approves each state rule; keep `UNVERIFIED` status in config |
| ESI ceiling/PwD values need current-year confirmation | wrong ESI liability | Effective-dated config and golden-master review by compliance owner |
| Bonus applicability/rate legal review pending | payroll misstatement | Leave bonus rule inactive by default; enable only with compliance approval |
| eSSL official API spec unavailable | adapter breaks on firmware/API change | Isolate adapter, contract tests against captured response fixtures, credential encryption, `UNVERIFIED` note retained |
| No email provider exists in code | notifications delayed | Build provider abstraction in P5; development mode logs simulated sends only |
| Flat `/process` clients remain in use | users bypass new lifecycle | Compatibility alias with validation; deprecation banner; remove only after frontend and demos migrate |
| AI hiring bias or proxy discrimination | legal/reputational exposure | Human review, adverse-impact monitoring, feature explanation, no protected attributes, no auto-reject |
| Candidate/employee PII leak | DPDP/contractual breach | Server-side masking, encryption, field permissions, audit sensitive reads, retention/erasure workflow |
| Duplicate punches or duplicate runs | wrong pay | Unique constraints, idempotency keys, DB locks, import dry-run report |
| Recruitment scope creep into full ATS/appraisal suite | schedule overrun | Keep named out-of-scope items; deliver core pipeline and onboarding handoff only |
| D4 attribute-level policy is cross-cutting | HR blocked if Identity policy layer slips | Define HR field policy in P0; implement shared serializer policy; waive only with CTO approval |
| Outbox/workflow engine not yet durable | lost cross-module events | P0 verifies outbox readiness before P2/P4; do not rely on in-process bus for production |

---

## 18. Definition of Done

- [ ] Alembic migration(s) created, reversible, applied from empty DB, and `alembic check` clean.
- [ ] Every HR model field is documented; FKs indexed; state guards covered by tests.
- [ ] I1: no duplicate employee/customer/user/channel tables; cross-module effects use service calls/events.
- [ ] I3: payroll finalization posts a balanced Finance journal; remittance and payment journals exist.
- [ ] I4: finalized payroll documents are immutable; corrections are reversals/replacements.
- [ ] I5: every HR document has an explicit state machine with named guards.
- [ ] I6: tenant scoping and audit rows are tested, including background jobs and agent actions.
- [ ] Statutory engine has golden-master tests and compliance-review sign-off for PF, ESI, TDS, PT, gratuity, and bonus rules used in production.
- [ ] Rule snapshots are immutable and linked from every payslip.
- [ ] ESSL import is idempotent, encrypted, and reconciles to daily summaries.
- [ ] Leave balances are append-only, audited, and cannot go negative except for configured unpaid leave.
- [ ] Recruitment pipeline, interview scorecards, offer approval, and human-only offer acceptance are tested end-to-end.
- [ ] WhatsApp/email notifications require consent/opt-in and write through Integrations.
- [ ] HR AI signals are read-only, explainable, reviewed, and excluded from autonomous employment decisions.
- [ ] D4 field masking is enforced server-side for salary, bank, PAN, Aadhaar, statutory IDs, and candidate PII.
- [ ] Permission codes and role templates are registered in `permissions_catalog.py`; frontend nav/actions match backend permissions.
- [ ] Events publish through the outbox; at least one HR subscriber integration test is green.
- [ ] OpenAPI snapshot generated and checked for breaking changes.
- [ ] Idempotency verified for payroll generate/finalize/pay, ESSL import, offer accept, and notification sends.
- [ ] One Playwright happy path for payroll and one for recruitment onboarding.
- [ ] One demo screen in the React shell for statutory payroll and one for hiring pipeline.
- [ ] Performance targets met: list p95 < 300 ms at 100k rows, payroll 500 employees < 5 s.
- [ ] Runbook covers deployment, rollback, parallel payroll, compliance export, and reconciliation report.
- [ ] `docs/PLAN-CONFORMANCE-CHECKLIST.md` row updated.
