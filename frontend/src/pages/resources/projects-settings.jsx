import { Link, useSearchParams } from 'react-router-dom'
import {
  Activity,
  BadgeIndianRupee,
  BookOpen,
  CalendarDays,
  ClipboardList,
  Database,
  FileText,
  GitBranch,
  Layers,
  Receipt,
  Settings,
  Upload,
  Users,
  Wallet,
  Workflow,
} from 'lucide-react'
import { Ref, Status } from '../../components/cells'
import {
  dateCol,
  makePage,
  moneyCol,
  qtyCol,
  refCol,
  refField,
  selectField,
  statusCol,
} from './projects'

function ProjectScoped({ Component }) {
  const [params] = useSearchParams()
  const projectId = params.get('project_id')
  return <Component key={projectId ?? 'all'} defaultFilters={projectId ? { project_id: projectId } : {}} />
}

const statuses = ['active', 'inactive', 'draft', 'archived']

const LabelsBase = makePage({
  title: 'Labels',
  eyebrow: 'Project settings',
  description: 'Project-specific labels for work item classification.',
  endpoint: '/projects/labels',
  permission: 'projects.label',
  emptyIcon: Layers,
  columns: [
    { key: 'name', label: 'Label' },
    { key: 'color', label: 'Color', render: (row) => <span className="badge">{row.color ?? '—'}</span> },
    refCol('project_id', 'Project', 'projects'),
    statusCol(),
  ],
  fields: [
    refField('project_id', 'Project', 'projects', true),
    { name: 'name', label: 'Name', required: true },
    { name: 'color', label: 'Color', default: 'stone' },
    selectField('status', 'Status', statuses, 'active'),
  ],
})

const CustomFieldsBase = makePage({
  title: 'Custom fields',
  eyebrow: 'Project settings',
  description: 'Define typed fields for work items and other PM entities.',
  endpoint: '/projects/custom-fields',
  permission: 'projects.customfield',
  emptyIcon: Settings,
  columns: [
    { key: 'label', label: 'Field' },
    { key: 'code', label: 'Code' },
    { key: 'entity_type', label: 'Entity type' },
    { key: 'type', label: 'Type', render: (row) => <span className="badge">{row.type ?? '—'}</span> },
    statusCol(),
  ],
  fields: [
    { name: 'entity_type', label: 'Entity type', required: true, default: 'work_item' },
    { name: 'code', label: 'Code', required: true },
    { name: 'label', label: 'Label', required: true },
    selectField('type', 'Type', ['text', 'textarea', 'number', 'date', 'select', 'multiselect', 'checkbox'], 'text'),
    { name: 'options_json', label: 'Options JSON', type: 'json', help: 'Array of allowed values for select fields.' },
    { name: 'visible_roles', label: 'Visible roles JSON', type: 'json', help: 'Empty list means all roles.' },
    { name: 'required', label: 'Required', type: 'checkbox' },
    selectField('status', 'Status', statuses, 'active'),
  ],
})

const FieldValuesBase = makePage({
  title: 'Field values',
  eyebrow: 'Project settings',
  description: 'Stored values for custom fields.',
  endpoint: '/projects/field-values',
  permission: 'projects.fieldvalue',
  emptyIcon: Database,
  columns: [
    refCol('work_item_id', 'Work item', 'workItems'),
    refCol('field_id', 'Custom field', 'customFields'),
    { key: 'value_json', label: 'Value', render: (row) => <span className="font-mono text-xs">{JSON.stringify(row.value_json ?? {})}</span> },
    qtyCol('version', 'Version'),
  ],
  fields: [
    refField('work_item_id', 'Work item', 'workItems', true),
    refField('field_id', 'Custom field', 'customFields', true),
    { name: 'value_json', label: 'Value JSON', type: 'json', required: true },
    { name: 'version', label: 'Version', type: 'number', default: 1 },
  ],
})

const WorkflowsBase = makePage({
  title: 'Workflows',
  eyebrow: 'Project settings',
  description: 'Workflow schemes, statuses and status categories.',
  endpoint: '/projects/workflows',
  permission: 'projects.workflow',
  emptyIcon: Workflow,
  columns: [
    { key: 'name', label: 'Scheme' },
    { key: 'entity_type', label: 'Entity type' },
    { key: 'work_item_type', label: 'Work item type' },
    { key: 'statuses_json', label: 'Statuses', render: (row) => <span className="text-xs text-muted">{Array.isArray(row.statuses_json) ? row.statuses_json.join(', ') : '—'}</span> },
    statusCol(),
  ],
  fields: [
    { name: 'name', label: 'Name', required: true },
    { name: 'entity_type', label: 'Entity type', required: true, default: 'work_item' },
    { name: 'work_item_type', label: 'Work item type' },
    { name: 'statuses_json', label: 'Statuses JSON', type: 'json' },
    { name: 'status_categories_json', label: 'Status categories JSON', type: 'json' },
    selectField('status', 'Status', statuses, 'active'),
  ],
})

const TransitionsBase = makePage({
  title: 'Transitions',
  eyebrow: 'Project settings',
  description: 'Allowed workflow events, guards and side effects.',
  endpoint: '/projects/transitions',
  permission: 'projects.transition',
  emptyIcon: GitBranch,
  columns: [
    refCol('scheme_id', 'Scheme', 'workflows'),
    { key: 'from_status', label: 'From' },
    { key: 'event', label: 'Event' },
    { key: 'to_status', label: 'To' },
    statusCol(),
  ],
  fields: [
    refField('scheme_id', 'Scheme', 'workflows', true),
    { name: 'from_status', label: 'From status', required: true },
    { name: 'event', label: 'Event', required: true },
    { name: 'to_status', label: 'To status', required: true },
    { name: 'guard_code', label: 'Guard code' },
    { name: 'required_role', label: 'Required role' },
    { name: 'required_fields_json', label: 'Required fields JSON', type: 'json' },
    { name: 'side_effects_json', label: 'Side effects JSON', type: 'json' },
    selectField('status', 'Status', statuses, 'active'),
  ],
})

const TemplatesBase = makePage({
  title: 'Templates',
  eyebrow: 'Project settings',
  description: 'Project and work item templates used by intake and setup.',
  endpoint: '/projects/templates',
  permission: 'projects.template',
  emptyIcon: BookOpen,
  columns: [
    { key: 'name', label: 'Template' },
    { key: 'type', label: 'Type' },
    refCol('workflow_scheme_id', 'Workflow', 'workflows'),
    { key: 'default_billing_type', label: 'Billing type' },
    statusCol(),
  ],
  fields: [
    { name: 'name', label: 'Name', required: true },
    { name: 'type', label: 'Type', required: true, default: 'project' },
    refField('workflow_scheme_id', 'Workflow scheme', 'workflows'),
    { name: 'structure_json', label: 'Structure JSON', type: 'json' },
    { name: 'checklist_json', label: 'Checklist JSON', type: 'json' },
    selectField('default_billing_type', 'Default billing type', ['fixed', 'time_and_material', 'milestone', 'non_billable', 'internal'], 'time_and_material'),
    selectField('status', 'Status', statuses, 'active'),
  ],
})

const ApprovalsRegisterBase = makePage({
  title: 'Approvals register',
  eyebrow: 'Project governance',
  description: 'Approval records created by lifecycle, intake and baseline controls.',
  endpoint: '/projects/approvals',
  permission: 'projects.approval',
  canCreate: false,
  canDelete: false,
  emptyIcon: ClipboardList,
  columns: [
    { key: 'approval_type', label: 'Type' },
    { key: 'entity_type', label: 'Entity', render: (row) => `${row.entity_type ?? ''} ${String(row.entity_id ?? '').slice(0, 8)}`.trim() },
    refCol('approver_employee_id', 'Approver', 'employees'),

    statusCol(),
    dateCol('decision_at', 'Decided'),
  ],
  fields: [
    { name: 'entity_type', label: 'Entity type', required: true, default: 'project' },
    { name: 'entity_id', label: 'Entity ID', required: true },
    { name: 'approval_type', label: 'Approval type', required: true },
    refField('approver_employee_id', 'Approver', 'employees'),
    selectField('status', 'Status', ['pending', 'approved', 'rejected'], 'pending'),
    { name: 'decision', label: 'Decision' },
    { name: 'due_at', label: 'Due at', type: 'datetime' },
    { name: 'comments', label: 'Comments', type: 'textarea' },
  ],
})

const BaselinesBase = makePage({
  title: 'Baselines',
  eyebrow: 'Project schedule',
  description: 'Approved schedule snapshots created from the Gantt workspace.',
  endpoint: '/projects/baselines',
  permission: 'projects.baseline',
  canCreate: false,
  canEdit: false,
  canDelete: false,
  emptyIcon: CalendarDays,
  columns: [
    refCol('project_id', 'Project', 'projects'),
    { key: 'name', label: 'Baseline' },
    statusCol(),
    dateCol('approved_at', 'Approved'),
  ],
  fields: [],
})

const BaselineSnapshotsBase = makePage({
  title: 'Baseline snapshots',
  eyebrow: 'Project schedule',
  description: 'Captured project and work item values for each approved baseline.',
  endpoint: '/projects/baseline-snapshots',
  permission: 'projects.baselinesnapshot',
  canCreate: false,
  canEdit: false,
  canDelete: false,
  emptyIcon: Database,
  columns: [
    refCol('baseline_id', 'Baseline', 'baselines'),
    { key: 'entity_type', label: 'Entity type' },
    { key: 'entity_id', label: 'Entity ID', render: (row) => String(row.entity_id ?? '').slice(0, 8) },
    { key: 'snapshot_json', label: 'Snapshot', render: (row) => <span className="font-mono text-xs">{JSON.stringify(row.snapshot_json ?? {})}</span> },
    dateCol('captured_at', 'Captured'),
  ],
  fields: [],
})

const ReleasesBase = makePage({
  title: 'Releases',
  eyebrow: 'Projects',
  description: 'Planned releases and their linked work items.',
  endpoint: '/projects/releases',
  permission: 'projects.release',
  emptyIcon: Layers,
  columns: [
    refCol('project_id', 'Project', 'projects'),
    { key: 'name', label: 'Release' },
    dateCol('release_date', 'Release date'),
    statusCol(),
  ],
  fields: [
    refField('project_id', 'Project', 'projects', true),
    { name: 'name', label: 'Name', required: true },
    { name: 'release_date', label: 'Release date', type: 'date' },
    { name: 'work_items_json', label: 'Work items JSON', type: 'json' },
    selectField('status', 'Status', ['planned', 'in_progress', 'released', 'cancelled'], 'planned'),
  ],
})

const WorkItemLinksBase = makePage({
  title: 'Work item links',
  eyebrow: 'Projects',
  description: 'Blocked-by, duplicate-of and related links between work items.',
  endpoint: '/projects/work-item-links',
  permission: 'projects.workitemlink',
  emptyIcon: GitBranch,
  columns: [
    refCol('work_item_id', 'Source', 'workItems'),
    refCol('linked_work_item_id', 'Linked item', 'workItems'),
    { key: 'link_type', label: 'Link type', render: (row) => <Status value={row.link_type} /> },
  ],
  fields: [
    refField('work_item_id', 'Source work item', 'workItems', true),
    refField('linked_work_item_id', 'Linked work item', 'workItems', true),
    selectField('link_type', 'Link type', ['relates_to', 'blocked_by', 'duplicate_of', 'caused_by'], 'relates_to'),
  ],
})

const RetrospectivesBase = makePage({
  title: 'Retrospectives',
  eyebrow: 'Projects',
  description: 'Sprint retrospectives and follow-up actions.',
  endpoint: '/projects/retrospectives',
  permission: 'projects.retrospective',
  emptyIcon: BookOpen,
  columns: [
    refCol('project_id', 'Project', 'projects'),
    refCol('sprint_id', 'Sprint', 'sprints'),
    { key: 'what_went_well', label: 'Went well' },
    { key: 'what_did_not', label: 'Did not' },
    statusCol(),
  ],
  fields: [
    refField('project_id', 'Project', 'projects', true),
    refField('sprint_id', 'Sprint', 'sprints'),
    { name: 'what_went_well', label: 'What went well', type: 'textarea' },
    { name: 'what_did_not', label: 'What did not go well', type: 'textarea' },
    { name: 'actions_json', label: 'Actions JSON', type: 'json' },
    refField('facilitator_id', 'Facilitator', 'users'),
    selectField('status', 'Status', ['draft', 'published', 'closed'], 'draft'),
  ],
})

const TimesheetEntriesBase = makePage({
  title: 'Timesheet entries',
  eyebrow: 'Project finance',
  description: 'Link approved time entries to employee timesheets.',
  endpoint: '/projects/timesheet-entries',
  permission: 'projects.timesheetentry',
  emptyIcon: Receipt,
  columns: [
    refCol('timesheet_id', 'Timesheet', 'timesheets'),
    refCol('time_entry_id', 'Time entry', 'timeEntries'),
  ],
  fields: [
    refField('timesheet_id', 'Timesheet', 'timesheets', true),
    refField('time_entry_id', 'Time entry', 'timeEntries', true),
  ],
})

const BillingLinesBase = makePage({
  title: 'Billing lines',
  eyebrow: 'Project finance',
  description: 'Billable source lines attached to a billing run.',
  endpoint: '/projects/billing-lines',
  permission: 'projects.billingline',
  canCreate: false,
  canEdit: false,
  canDelete: false,
  emptyIcon: Receipt,
  columns: (can) => [
    refCol('billing_run_id', 'Billing run', 'billingRuns'),
    { key: 'source_type', label: 'Source' },
    { key: 'description', label: 'Description' },
    qtyCol('quantity', 'Qty'),
    ...(can('projects.finance.read') ? [moneyCol('amount', 'Amount')] : []),
    statusCol(),
  ],
  fields: [],
})

const InvoiceLinksBase = makePage({
  title: 'Invoice links',
  eyebrow: 'Project finance',
  description: 'Finance invoice IDs linked to projects and billing runs.',
  endpoint: '/projects/invoice-links',
  permission: 'projects.invoicelink',
  emptyIcon: BadgeIndianRupee,
  columns: (can) => [
    { key: 'finance_invoice_id', label: 'Invoice ID', render: (row) => <Ref lookup="invoices" id={row.finance_invoice_id} /> },
    refCol('project_id', 'Project', 'projects'),
    refCol('billing_run_id', 'Billing run', 'billingRuns'),
    ...(can('projects.finance.read') ? [moneyCol('amount', 'Amount')] : []),
    statusCol(),
  ],
  fields: [
    refField('finance_invoice_id', 'Finance invoice', 'invoices', true),
    refField('project_id', 'Project', 'projects', true),
    refField('billing_run_id', 'Billing run', 'billingRuns'),
    { name: 'amount', label: 'Amount', type: 'number', default: 0 },
    selectField('status', 'Status', ['open', 'paid', 'cancelled'], 'open'),
    { name: 'paid_at', label: 'Paid at', type: 'datetime' },
  ],
})

const BudgetRevisionsBase = makePage({
  title: 'Budget revisions',
  eyebrow: 'Project finance',
  description: 'Approval trail for budget changes.',
  endpoint: '/projects/budget-revisions',
  permission: 'projects.budgetrevision',
  emptyIcon: Wallet,
  columns: [
    refCol('budget_id', 'Budget', 'budgets'),
    { key: 'reason', label: 'Reason' },
    refCol('approved_by_id', 'Approved by', 'users'),
    statusCol(),
  ],
  fields: [
    refField('budget_id', 'Budget', 'budgets', true),
    { name: 'reason', label: 'Reason', type: 'textarea' },
    { name: 'change_json', label: 'Change JSON', type: 'json' },
    refField('approved_by_id', 'Approved by', 'users'),
    selectField('status', 'Status', ['pending', 'approved', 'rejected'], 'pending'),
  ],
})

const EmployeeSkillsBase = makePage({
  title: 'Employee skills',
  eyebrow: 'Project resources',
  description: 'Skill codes and proficiency used for resource planning.',
  endpoint: '/projects/employee-skills',
  permission: 'projects.employeeskill',
  emptyIcon: Users,
  columns: [
    refCol('employee_id', 'Employee', 'employees'),
    { key: 'skill_code', label: 'Skill code' },
    qtyCol('proficiency', 'Proficiency'),
    statusCol(),
  ],
  fields: [
    refField('employee_id', 'Employee', 'employees', true),
    { name: 'skill_code', label: 'Skill code', required: true },
    { name: 'proficiency', label: 'Proficiency (1–5)', type: 'number', min: 1, default: 1 },
    { name: 'evidence_document_id', label: 'Evidence document ID', help: 'Store the file in Documents and paste its ID here.' },
    refField('verified_by_id', 'Verified by', 'users'),
    selectField('status', 'Status', statuses, 'active'),
  ],
})

const CapacityCalendarsBase = makePage({
  title: 'Capacity calendars',
  eyebrow: 'Project resources',
  description: 'Weekly employee capacity, leave and holiday hours.',
  endpoint: '/projects/capacity-calendars',
  permission: 'projects.capacitycalendar',
  emptyIcon: CalendarDays,
  columns: [
    refCol('employee_id', 'Employee', 'employees'),
    dateCol('week_start', 'Week start'),
    qtyCol('capacity_hours', 'Capacity'),
    qtyCol('planned_leave_hours', 'Leave'),
    qtyCol('holiday_hours', 'Holiday'),
    statusCol(),
  ],
  fields: [
    refField('employee_id', 'Employee', 'employees', true),
    { name: 'week_start', label: 'Week start', type: 'date', required: true },
    { name: 'capacity_hours', label: 'Capacity hours', type: 'number', default: 40 },
    { name: 'planned_leave_hours', label: 'Planned leave hours', type: 'number', default: 0 },
    { name: 'holiday_hours', label: 'Holiday hours', type: 'number', default: 0 },
    selectField('source', 'Source', ['hr', 'manual', 'integration'], 'hr'),
    selectField('status', 'Status', statuses, 'active'),
  ],
})

const WorkloadSnapshotsBase = makePage({
  title: 'Workload snapshots',
  eyebrow: 'Project resources',
  description: 'Computed weekly utilization and overallocation flags.',
  endpoint: '/projects/workload-snapshots',
  permission: 'projects.workload',
  canCreate: false,
  canEdit: false,
  canDelete: false,
  emptyIcon: Activity,
  columns: [
    refCol('employee_id', 'Employee', 'employees'),
    dateCol('week_start', 'Week start'),
    qtyCol('booked_hours', 'Booked'),
    qtyCol('available_hours', 'Available'),
    qtyCol('utilization_percent', 'Utilization %'),
    { key: 'overallocated', label: 'Overallocated', render: (row) => <Status value={row.overallocated ? 'escalated' : 'active'} /> },
  ],
  fields: [],
})

const IntegrationsBase = makePage({
  title: 'Integrations',
  eyebrow: 'Project settings',
  description: 'External provider links and sync configuration.',
  endpoint: '/projects/integrations',
  permission: 'projects.integration',
  emptyIcon: GitBranch,
  columns: [
    { key: 'provider', label: 'Provider' },
    { key: 'external_id', label: 'External ID' },
    { key: 'config_json', label: 'Config', render: (row) => <span className="font-mono text-xs">{JSON.stringify(row.config_json ?? {})}</span> },
    statusCol(),
    dateCol('last_sync_at', 'Last sync'),
  ],
  fields: [
    { name: 'provider', label: 'Provider', required: true },
    { name: 'external_id', label: 'External ID', required: true },
    { name: 'config_json', label: 'Config JSON', type: 'json' },
    selectField('status', 'Status', statuses, 'active'),
    { name: 'last_sync_at', label: 'Last sync', type: 'datetime' },
  ],
})

const ImportBatchesBase = makePage({
  title: 'Import batches',
  eyebrow: 'Project settings',
  description: 'Staging batches created in the Imports workspace.',
  endpoint: '/projects/import-batches',
  permission: 'projects.importbatch',
  canCreate: false,
  canEdit: false,
  canDelete: false,
  emptyIcon: Upload,
  columns: [
    { key: 'provider', label: 'Provider', render: (row) => <Status value={row.provider} /> },
    statusCol(),
    qtyCol('rows_total', 'Rows'),
    qtyCol('rows_imported', 'Imported'),
    qtyCol('rows_failed', 'Failed'),
    dateCol('created_at', 'Created'),
  ],
  fields: [],
  rowActions: () => [
    {
      label: 'Review import',
      render: (row) => (
        <Link
          to={`/projects/imports?batch=${row.id}`}
          title="Review import batch"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink"
        >
          <FileText size={15} />
        </Link>
      ),
    },
  ],
})

export const LabelsPage = () => <LabelsBase />
export const CustomFieldsPage = () => <CustomFieldsBase />
export const FieldValuesPage = () => <FieldValuesBase />
export const WorkflowsPage = () => <WorkflowsBase />
export const TransitionsPage = () => <TransitionsBase />
export const TemplatesPage = () => <TemplatesBase />
export const ApprovalsRegisterPage = () => <ApprovalsRegisterBase />
export const BaselinesPage = () => <ProjectScoped Component={BaselinesBase} />
export const BaselineSnapshotsPage = () => <BaselineSnapshotsBase />
export const ReleasesPage = () => <ProjectScoped Component={ReleasesBase} />
export const WorkItemLinksPage = () => <ProjectScoped Component={WorkItemLinksBase} />
export const RetrospectivesPage = () => <ProjectScoped Component={RetrospectivesBase} />
export const TimesheetEntriesPage = () => <TimesheetEntriesBase />
export const BillingLinesPage = () => <BillingLinesBase />
export const InvoiceLinksPage = () => <ProjectScoped Component={InvoiceLinksBase} />
export const BudgetRevisionsPage = () => <BudgetRevisionsBase />
export const EmployeeSkillsPage = () => <EmployeeSkillsBase />
export const CapacityCalendarsPage = () => <CapacityCalendarsBase />
export const WorkloadSnapshotsPage = () => <WorkloadSnapshotsBase />
export const IntegrationsPage = () => <IntegrationsBase />
export const ImportBatchesPage = () => <ImportBatchesBase />
