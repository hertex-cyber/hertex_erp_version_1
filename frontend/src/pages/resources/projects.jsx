import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Activity,
  ArrowDown,
  ArrowUp,
  BadgeCheck,
  Ban,
  BarChart3,
  BookOpen,
  BriefcaseBusiness,
  CalendarDays,
  Check,
  CheckCircle2,
  ClipboardList,
  Clock3,
  FileText,
  Flag,
  FolderKanban,
  GitBranch,
  Inbox,
  Layers,
  Link2,
  ListChecks,
  LockKeyhole,
  Play,
  Plus,
  Receipt,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldAlert,
  Sparkles,
  Target,
  Timer,
  UnlockKeyhole,
  Users,
  Wallet,
  Workflow,
  XCircle,
  Zap,
} from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { FormGrid, RemoteSelect } from '../../components/Form'
import { EmptyState, Modal, PageHeader, Spinner } from '../../components/ui'
import { DateCell, Money, Primary, Qty, Ref, Status, TypeBadge } from '../../components/cells'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel, num, pct, titleCase } from '../../lib/format'
import { fetchLookup } from '../../lib/lookups'
import { AI_ACTION_TYPES, aiActionScope, isProhibitedAiAction, topFeatures } from '../../lib/project-helpers'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

const PROJECT_STATUSES = ['draft', 'approval_pending', 'approved', 'active', 'on_hold', 'completed', 'cancelled', 'rejected']
const HEALTH = ['green', 'amber', 'red', 'unknown']
const BILLING_TYPES = ['fixed', 'time_and_material', 'milestone', 'non_billable', 'internal']
const METHODOLOGIES = ['agile', 'predictive', 'hybrid']
const PRIORITIES = ['low', 'medium', 'high', 'urgent']
const WORK_ITEM_STATUSES = ['backlog', 'todo', 'in_progress', 'blocked', 'in_review', 'done', 'accepted', 'closed', 'cancelled']
const WORK_ITEM_TYPES = ['epic', 'feature', 'story', 'task', 'bug', 'enabler', 'subtask']
const SPRINT_STATUSES = ['planned', 'active', 'completed', 'cancelled']
const MILESTONE_STATUSES = ['planned', 'reached', 'accepted', 'billed', 'paid', 'cancelled']
const DEPENDENCY_TYPES = ['FS', 'SS', 'FF', 'SF']
const DEPENDENCY_STATUSES = ['proposed', 'active', 'resolved', 'cancelled']
const TIME_ENTRY_STATUSES = ['draft', 'submitted', 'approved', 'invoiced', 'paid', 'rejected']
const TIMESHEET_STATUSES = ['draft', 'submitted', 'approved', 'rejected']
const EXPENSE_CATEGORIES = ['travel', 'material', 'software', 'subcontract', 'meals', 'other']
const EXPENSE_STATUSES = ['draft', 'submitted', 'approved', 'invoiced', 'paid', 'rejected']
const COST_TYPES = ['labour', 'expense', 'material', 'subcontract', 'overhead']
const BILLING_STATUSES = ['draft', 'review', 'approved', 'invoiced', 'failed']
const BOOKING_STATUSES = ['requested', 'confirmed', 'fulfilled', 'cancelled']
const RISK_STATUSES = ['identified', 'analysing', 'mitigated', 'escalated', 'closed', 'cancelled']
const ISSUE_STATUSES = ['open', 'triaged', 'in_progress', 'resolved', 'closed', 'cancelled']
const SEVERITIES = ['low', 'medium', 'high', 'critical']
const CHANGE_STATUSES = ['draft', 'submitted', 'approved', 'rejected', 'applied']
const GOAL_STATUSES = ['active', 'on_track', 'at_risk', 'completed', 'cancelled']
const AI_ACTION_STATUSES = ['proposed', 'approved', 'executed', 'rejected', 'reversed', 'failed']
const AUTOMATION_STATUSES = ['active', 'paused', 'draft', 'cancelled']
const OUTBOX_STATUSES = ['pending', 'published', 'failed']

export function useCan() {
  return useAuth((state) => state.can)
}

export function makePage(config) {
  return function ConfiguredResourcePage(props) {
    const can = useCan()
    const resolved = { ...config }
    for (const key of [
      'columns',
      'fields',
      'editFields',
      'filters',
      'rowActions',
      'headerActions',
      'readPermission',
      'createPermission',
      'updatePermission',
      'deletePermission',
      'defaultFilters',
    ]) {
      if (typeof config[key] === 'function') resolved[key] = config[key](can)
    }
    if (props?.defaultFilters) {
      resolved.defaultFilters = { ...(resolved.defaultFilters ?? {}), ...props.defaultFilters }
    }
    return <ResourcePage {...resolved} />
  }
}

export function pmAction(can, { label, icon: Icon, endpoint, method = 'post', body, permission, show, tone, success, description }) {
  return {
    label,
    icon: Icon,
    tone,
    show: (row) => Boolean(can(permission)) && (!show || show(row)),
    onClick: async (row, { reload }) => {
      try {
        await api[method](endpoint(row), body?.(row))
        toast.success(success ?? label, description ?? 'The action completed successfully.')
        reload()
      } catch (error) {
        toast.error('Could not complete action', apiErrorMessage(error))
      }
    },
  }
}

function transition(can, { label, icon: Icon, event, endpoint, permission, from, tone }) {
  return pmAction(can, {
    label,
    icon: Icon,
    endpoint,
    permission,
    tone,
    body: () => ({ event }),
    show: (row) => !from || from.includes(row.status),
  })
}

function eventActions(can, endpoint, permission, events) {
  return events.map((event) => transition(can, { endpoint, permission, ...event }))
}

const WORK_ITEM_EVENTS = [
  { event: 'refine', label: 'Refine', icon: ClipboardList, from: ['backlog'] },
  { event: 'start', label: 'Start work', icon: Play, from: ['todo'] },
  { event: 'block', label: 'Block', icon: Ban, from: ['in_progress'], tone: 'danger' },
  { event: 'unblock', label: 'Unblock', icon: UnlockKeyhole, from: ['blocked'] },
  { event: 'submit_review', label: 'Submit for review', icon: Send, from: ['in_progress'] },
  { event: 'approve', label: 'Approve', icon: BadgeCheck, from: ['in_review'], tone: 'positive' },
  { event: 'request_change', label: 'Request changes', icon: RotateCcw, from: ['in_review'] },
  { event: 'accept', label: 'Accept', icon: CheckCircle2, from: ['done'], tone: 'positive' },
  { event: 'close', label: 'Close', icon: LockKeyhole, from: ['accepted'] },
  { event: 'reopen', label: 'Reopen', icon: RefreshCw, from: ['done', 'accepted', 'closed', 'cancelled'] },
]

export function ToolButton({ label, icon: Icon, permission, endpoint, body, params, method = 'post', success, description, onDone }) {
  const can = useCan()
  const [busy, setBusy] = useState(false)
  if (!can(permission)) return null
  const run = async () => {
    setBusy(true)
    try {
      await api[method](endpoint, body, params ? { params } : undefined)
      toast.success(success ?? label, description ?? 'The action completed successfully.')
      onDone?.()
    } catch (error) {
      toast.error('Could not complete action', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }
  return (
    <button type="button" className="btn-secondary" onClick={run} disabled={busy}>
      {busy ? <Spinner className="h-4 w-4" /> : <Icon size={15} />} {label}
    </button>
  )
}

export function ActionDialog({ label, icon: Icon, permission, title, description, fields, endpoint, payload, success, onDone }) {
  const can = useCan()
  const [open, setOpen] = useState(false)
  const [values, setValues] = useState({})
  const [busy, setBusy] = useState(false)
  if (!can(permission)) return null

  const openDialog = () => {
    setValues(Object.fromEntries(fields.map((field) => [field.name, field.default ?? ''])))
    setOpen(true)
  }

  const submit = async () => {
    setBusy(true)
    try {
      await api.post(endpoint, typeof payload === 'function' ? payload(values) : payload ?? values)
      toast.success(success ?? label, 'The request was submitted.')
      setOpen(false)
      onDone?.()
    } catch (error) {
      toast.error('Could not complete action', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button type="button" className="btn-primary" onClick={openDialog}>
        {Icon ? <Icon size={16} /> : null} {label}
      </button>
      <Modal
        open={open}
        onClose={() => !busy && setOpen(false)}
        title={title ?? label}
        description={description}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)} disabled={busy}>
              Cancel
            </button>
            <button type="button" className="btn-primary" onClick={submit} disabled={busy}>
              {busy && <Spinner className="h-4 w-4" />} Submit
            </button>
          </>
        }
      >
        <FormGrid fields={fields} values={values} onChange={(name, value) => setValues((current) => ({ ...current, [name]: value }))} />
      </Modal>
    </>
  )
}

export const statusCol = (key = 'status', label = 'Status') => ({
  key,
  label,
  render: (row) => <Status value={row[key]} />,
})
export const refCol = (key, label, lookup) => ({ key, label, render: (row) => <Ref lookup={lookup} id={row[key]} /> })
export const dateCol = (key, label) => ({ key, label, render: (row) => <DateCell value={row[key]} /> })
export const moneyCol = (key, label) => ({
  key,
  label,
  align: 'right',
  render: (row) => <Money value={row[key]} currency={row.currency ?? row.project_currency} restricted />,
})
export const qtyCol = (key, label) => ({ key, label, align: 'right', render: (row) => <Qty value={row[key]} /> })
export const refField = (name, label, lookup, required = false) => ({
  name,
  label,
  type: 'reference',
  lookup,
  required,
})
export const selectField = (name, label, options, defaultValue, required = false) => ({
  name,
  label,
  type: 'select',
  options,
  default: defaultValue,
  required,
})

export const ProjectsPage = makePage({
  eyebrow: 'Projects',
  title: 'Projects',
  description: 'Delivery containers with lifecycle, health, customer and schedule.',
  endpoint: '/projects',
  permission: 'projects.project',
  createLabel: 'New project',
  searchPlaceholder: 'Search projects, codes, numbers…',
  filters: (can) => [
    { name: 'status', label: 'All statuses', options: PROJECT_STATUSES },
    { name: 'health', label: 'All health', options: HEALTH },
    { name: 'billing_type', label: 'All billing types', options: BILLING_TYPES },
    ...(can('projects.finance.read') ? [{ name: 'priority', label: 'All priorities', options: PRIORITIES }] : []),
  ],
  emptyIcon: FolderKanban,
  columns: (can) => [
    {
      key: 'name',
      label: 'Project',
      render: (row) => <Primary title={row.name} subtitle={`${row.number ?? row.code} · ${row.client_name || 'Internal'}`} />,
    },
    { key: 'number', label: 'Number' },
    refCol('portfolio_id', 'Portfolio', 'portfolios'),
    refCol('program_id', 'Program', 'programs'),
    { key: 'client_name', label: 'Client' },
    statusCol(),
    statusCol('health', 'Health'),
    ...(can('projects.finance.read') ? [moneyCol('budget', 'Budget')] : []),
    refCol('manager_employee_id', 'Manager', 'employees'),
    dateCol('start_date', 'Starts'),
    dateCol('end_date', 'Ends'),
  ],
  rowActions: (can) => [
    {
      label: 'Open workspace',
      render: (row) => (
        <Link
          to={`/projects/projects/${row.id}`}
          title="Open project workspace"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink"
        >
          <FolderKanban size={15} />
        </Link>
      ),
    },
    pmAction(can, {
      label: 'Submit for approval',
      icon: Send,
      endpoint: (row) => `/projects/projects/${row.id}/submit`,
      body: () => ({ event: 'submit' }),
      permission: 'projects.project.update',
      show: (row) => row.status === 'draft',
    }),
    pmAction(can, {
      label: 'Approve',
      icon: BadgeCheck,
      endpoint: (row) => `/projects/projects/${row.id}/approve`,
      body: () => ({ event: 'approve' }),
      permission: 'projects.approval.create',
      tone: 'positive',
      show: (row) => row.status === 'approval_pending',
    }),
    pmAction(can, {
      label: 'Activate',
      icon: Play,
      endpoint: (row) => `/projects/projects/${row.id}/activate`,
      body: () => ({ event: 'activate' }),
      permission: 'projects.project.update',
      tone: 'positive',
      show: (row) => row.status === 'approved',
    }),
    pmAction(can, {
      label: 'Complete',
      icon: CheckCircle2,
      endpoint: (row) => `/projects/projects/${row.id}/complete`,
      body: () => ({ event: 'complete' }),
      permission: 'projects.project.update',
      tone: 'positive',
      show: (row) => row.status === 'active',
    }),
  ],
  fields: (can) => [
    { name: 'name', label: 'Project name', required: true },
    { name: 'code', label: 'Project code', required: true },
    { name: 'client_name', label: 'Client' },
    refField('customer_id', 'Customer', 'customers'),
    refField('portfolio_id', 'Portfolio', 'portfolios'),
    refField('program_id', 'Program', 'programs'),
    refField('manager_employee_id', 'Manager', 'employees'),
    selectField('billing_type', 'Billing type', BILLING_TYPES, 'time_and_material'),
    selectField('methodology', 'Methodology', METHODOLOGIES, 'agile'),
    selectField('priority', 'Priority', PRIORITIES, 'medium'),
    selectField('status', 'Status', PROJECT_STATUSES, 'draft'),
    selectField('health', 'Health', HEALTH, 'unknown'),
    { name: 'start_date', label: 'Start date', type: 'date', default: 'today' },
    { name: 'end_date', label: 'End date', type: 'date' },
    ...(can('projects.finance.read')
      ? [
          { name: 'budget', label: 'Budget', type: 'number', default: 0 },
          { name: 'contract_value', label: 'Contract value', type: 'number', default: 0 },
        ]
      : []),
    { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
  ].filter(Boolean),
  canEdit: false,
})

export const WorkItemsPage = makePage({
  eyebrow: 'Projects',
  title: 'Work items',
  description: 'Backlog, boards, workflow transitions, estimates and ownership.',
  endpoint: '/projects/work-items',
  permission: 'projects.workitem',
  createLabel: 'New work item',
  searchPlaceholder: 'Search titles or work item numbers…',
  filters: [
    { name: 'status', label: 'All statuses', options: WORK_ITEM_STATUSES },
    { name: 'work_item_type', label: 'All types', options: WORK_ITEM_TYPES },
    { name: 'priority', label: 'All priorities', options: PRIORITIES },
    { name: 'project_id', label: 'All projects', options: (rows) => [...new Set(rows.map((row) => row.project_id).filter(Boolean))].map((id) => ({ value: id, label: id })) },
    { name: 'assignee_id', label: 'All assignees', options: (rows) => [...new Set(rows.map((row) => row.assignee_id).filter(Boolean))].map((id) => ({ value: id, label: id })) },
  ],
  emptyIcon: ListChecks,
  columns: [
    {
      key: 'title',
      label: 'Work item',
      render: (row) => <Primary title={row.title} subtitle={`${row.number ?? ''} · ${titleCase(row.work_item_type)}`} />,
    },
    refCol('project_id', 'Project', 'projects'),
    { key: 'work_item_type', label: 'Type', render: (row) => <TypeBadge value={row.work_item_type} /> },
    statusCol(),
    { key: 'priority', label: 'Priority', render: (row) => <TypeBadge value={row.priority} /> },
    refCol('employee_id', 'Assignee', 'employees'),
    refCol('sprint_id', 'Sprint', 'sprints'),
    qtyCol('story_points', 'Points'),
    dateCol('due_date', 'Due'),
  ],
  rowActions: (can) => [
    ...eventActions(
      can,
      (row) => `/projects/work-items/${row.id}/transition`,
      'projects.workitem.update',
      WORK_ITEM_EVENTS,
    ),
    {
      label: 'Open project',
      show: (row) => Boolean(row.project_id),
      render: (row) => (
        <Link
          to={`/projects/projects/${row.project_id}`}
          title="Open project workspace"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink"
        >
          <FolderKanban size={15} />
        </Link>
      ),
    },
    pmAction(can, {
      label: 'Run automation',
      icon: Zap,
      endpoint: () => '/projects/automation/runs',
      body: (row) => ({ trigger_entity: 'work_item', trigger_id: row.id }),
      permission: 'projects.automation.run',
      success: 'Automation triggered',
    }),
  ],
  fields: [
    refField('project_id', 'Project', 'projects', true),
    { name: 'title', label: 'Title', required: true },
    selectField('work_item_type', 'Type', WORK_ITEM_TYPES, 'task'),
    selectField('status', 'Status', WORK_ITEM_STATUSES, 'backlog'),
    selectField('priority', 'Priority', PRIORITIES, 'medium'),
    refField('employee_id', 'Assignee', 'employees'),
    refField('assignee_id', 'Login user', 'users'),
    refField('sprint_id', 'Sprint', 'sprints'),
    refField('board_id', 'Board', 'boards'),
    refField('board_column_id', 'Board column', 'boardColumns', true),
    refField('parent_work_item_id', 'Parent work item', 'workItems'),
    { name: 'story_points', label: 'Story points', type: 'number', default: 0 },
    { name: 'estimated_hours', label: 'Estimated hours', type: 'number', default: 0 },
    { name: 'planned_hours', label: 'Planned hours', type: 'number', default: 0 },
    { name: 'start_date', label: 'Start date', type: 'date' },
    { name: 'due_date', label: 'Due date', type: 'date' },
    { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
  ],
  canEdit: false,
})
export const TasksPage = WorkItemsPage

export const BoardsPage = makePage({
  eyebrow: 'Projects',
  title: 'Boards',
  description: 'Kanban and Scrum board configurations with WIP settings.',
  endpoint: '/projects/boards',
  permission: 'projects.board',
  createLabel: 'New board',
  emptyIcon: Layers,
  columns: [
    { key: 'name', label: 'Board', render: (row) => <Primary title={row.name} subtitle={titleCase(row.type)} /> },
    refCol('project_id', 'Project', 'projects'),
    { key: 'type', label: 'Type', render: (row) => <TypeBadge value={row.type} /> },
    { key: 'wip_enabled', label: 'WIP limits', render: (row) => <Status value={row.wip_enabled ? 'active' : 'inactive'} /> },
    statusCol(),
  ],
  fields: [
    refField('project_id', 'Project', 'projects', true),
    { name: 'name', label: 'Board name', required: true },
    selectField('type', 'Type', ['kanban', 'scrum', 'timeline'], 'kanban'),
    { name: 'wip_enabled', label: 'Enforce WIP limits', type: 'checkbox' },
    selectField('status', 'Status', ['active', 'archived'], 'active'),
  ],
})

export const BoardColumnsPage = makePage({
  eyebrow: 'Projects',
  title: 'Board columns',
  description: 'Workflow columns, sequence and WIP thresholds.',
  endpoint: '/projects/board-columns',
  permission: 'projects.boardcolumn',
  createLabel: 'New column',
  filters: [{ name: 'status_category', label: 'All categories', options: ['todo', 'active', 'done', 'cancelled'] }],
  emptyIcon: ColumnsIcon,
  columns: [
    { key: 'name', label: 'Column', render: (row) => <Primary title={row.name} subtitle={`Sequence ${row.sequence ?? '—'}`} /> },
    refCol('board_id', 'Board', 'boards'),
    qtyCol('sequence', 'Sequence'),
    qtyCol('wip_limit', 'WIP limit'),
    { key: 'status_category', label: 'Category', render: (row) => <TypeBadge value={row.status_category} /> },
    statusCol(),
  ],
  fields: [
    refField('board_id', 'Board', 'boards', true),
    { name: 'name', label: 'Column name', required: true },
    { name: 'sequence', label: 'Sequence', type: 'number', default: 1 },
    { name: 'wip_limit', label: 'WIP limit', type: 'number' },
    selectField('status_category', 'Category', ['todo', 'active', 'done', 'cancelled'], 'todo'),
    selectField('status', 'Status', ['active', 'inactive'], 'active'),
  ],
})

export const SprintsPage = makePage({
  eyebrow: 'Projects',
  title: 'Sprints',
  description: 'Timeboxed delivery cycles with capacity and velocity inputs.',
  endpoint: '/projects/sprints',
  permission: 'projects.sprint',
  createLabel: 'New sprint',
  filters: [{ name: 'status', label: 'All statuses', options: SPRINT_STATUSES }],
  emptyIcon: Timer,
  columns: [
    { key: 'name', label: 'Sprint', render: (row) => <Primary title={row.name} subtitle={row.number} /> },
    refCol('project_id', 'Project', 'projects'),
    dateCol('start_date', 'Starts'),
    dateCol('end_date', 'Ends'),
    qtyCol('capacity_hours', 'Hours'),
    qtyCol('capacity_points', 'Points'),
    statusCol(),
  ],
  rowActions: (can) =>
    eventActions(
      can,
      (row) => `/projects/sprints/${row.id}/transition`,
      'projects.sprint.update',
      [
        { event: 'start', label: 'Start sprint', icon: Play, from: ['planned'], tone: 'positive' },
        { event: 'complete', label: 'Complete sprint', icon: CheckCircle2, from: ['active'], tone: 'positive' },
        { event: 'cancel', label: 'Cancel sprint', icon: XCircle, from: ['planned', 'active'], tone: 'danger' },
      ],
    ),
  fields: [
    refField('project_id', 'Project', 'projects', true),
    { name: 'name', label: 'Sprint name', required: true },
    { name: 'start_date', label: 'Start date', type: 'date', default: 'today', required: true },
    { name: 'end_date', label: 'End date', type: 'date', required: true },
    { name: 'capacity_hours', label: 'Capacity hours', type: 'number', default: 0 },
    { name: 'capacity_points', label: 'Capacity points', type: 'number', default: 0 },
    { name: 'goal', label: 'Sprint goal', type: 'textarea', colSpan: 2 },
  ],
  canEdit: false,
})

export const MilestonesPage = makePage({
  eyebrow: 'Projects',
  title: 'Milestones',
  description: 'Dated deliverables with acceptance and billing status.',
  endpoint: '/projects/milestones',
  permission: 'projects.milestone',
  createLabel: 'New milestone',
  filters: [{ name: 'status', label: 'All statuses', options: MILESTONE_STATUSES }],
  emptyIcon: Flag,
  columns: (can) => [
    { key: 'name', label: 'Milestone', render: (row) => <Primary title={row.name} subtitle={row.acceptance_criteria || 'No acceptance criteria'} /> },
    refCol('project_id', 'Project', 'projects'),
    dateCol('due_date', 'Due'),
    ...(can('projects.finance.read') ? [moneyCol('amount', 'Amount')] : []),
    statusCol(),
    dateCol('accepted_at', 'Accepted'),
  ],
  rowActions: (can) =>
    eventActions(
      can,
      (row) => `/projects/milestones/${row.id}/transition`,
      'projects.milestone.update',
      [
        { event: 'reach', label: 'Mark reached', icon: Flag, from: ['planned'] },
        { event: 'accept', label: 'Accept', icon: BadgeCheck, from: ['reached'], tone: 'positive' },
        { event: 'bill', label: 'Mark billed', icon: Receipt, from: ['accepted'], tone: 'positive' },
        { event: 'paid', label: 'Mark paid', icon: CheckCircle2, from: ['billed'], tone: 'positive' },
      ],
    ),
  fields: (can) => [
    refField('project_id', 'Project', 'projects', true),
    { name: 'name', label: 'Milestone name', required: true },
    { name: 'due_date', label: 'Due date', type: 'date' },
    ...(can('projects.finance.read') ? [{ name: 'amount', label: 'Amount', type: 'number', default: 0 }] : []),
    { name: 'acceptance_criteria', label: 'Acceptance criteria', type: 'textarea', colSpan: 2 },
  ],
  canEdit: false,
})

export const DependenciesPage = makePage({
  eyebrow: 'Projects',
  title: 'Dependencies',
  description: ' schedule links with lead/lag and cycle-safe confirmation.',
  endpoint: '/projects/dependencies',
  permission: 'projects.dependency',
  canCreate: false,
  filters: [
    { name: 'status', label: 'All statuses', options: DEPENDENCY_STATUSES },
    { name: 'type', label: 'All types', options: DEPENDENCY_TYPES },
  ],
  headerActions: (
    <ActionDialog
      label="Add dependency"
      icon={Link2}
      permission="projects.schedule.create"
      title="Add dependency"
      description="Cycle detection runs when the link is created."
      endpoint="/projects/dependencies"
      fields={[
        refField('predecessor_id', 'Predecessor', 'workItems', true),
        refField('successor_id', 'Successor', 'workItems', true),
        selectField('type', 'Type', DEPENDENCY_TYPES, 'FS'),
        { name: 'lag_days', label: 'Lag days', type: 'number', default: 0 },
      ]}
    />
  ),
  emptyIcon: GitBranch,
  columns: [
    {
      key: 'predecessor_id',
      label: 'Predecessor',
      render: (row) => <Ref lookup="workItems" id={row.predecessor_id} />,
    },
    { key: 'successor_id', label: 'Successor', render: (row) => <Ref lookup="workItems" id={row.successor_id} /> },
    { key: 'type', label: 'Type', render: (row) => <TypeBadge value={row.type} /> },
    qtyCol('lag_days', 'Lag days'),
    statusCol(),
  ],
  rowActions: (can) =>
    eventActions(
      can,
      (row) => `/projects/dependencies/${row.id}/transition`,
      'projects.schedule.update',
      [
        { event: 'confirm', label: 'Confirm', icon: BadgeCheck, from: ['proposed'], tone: 'positive' },
        { event: 'resolve', label: 'Resolve', icon: CheckCircle2, from: ['active'], tone: 'positive' },
        { event: 'cancel', label: 'Cancel', icon: XCircle, from: ['proposed', 'active'], tone: 'danger' },
      ],
    ),
  canEdit: false,
})

export const PortfoliosPage = makePage({
  eyebrow: 'Projects',
  title: 'Portfolios',
  description: 'Strategic groups of programmes and projects with health tracking.',
  endpoint: '/projects/portfolios',
  permission: 'projects.portfolio',
  createLabel: 'New portfolio',
  filters: [
    { name: 'status', label: 'All statuses', options: ['active', 'archived'] },
    { name: 'health', label: 'All health', options: HEALTH },
  ],
  emptyIcon: BriefcaseBusiness,
  columns: (can) => [
    { key: 'name', label: 'Portfolio', render: (row) => <Primary title={row.name} subtitle={row.code} /> },
    refCol('owner_employee_id', 'Owner', 'employees'),
    statusCol('health', 'Health'),
    statusCol(),
    ...(can('projects.finance.read') ? [moneyCol('budget', 'Budget')] : []),
  ],
  fields: (can) => [
    { name: 'name', label: 'Portfolio name', required: true },
    { name: 'code', label: 'Code', required: true },
    refField('owner_employee_id', 'Owner', 'employees'),
    selectField('health', 'Health', HEALTH, 'unknown'),
    selectField('status', 'Status', ['active', 'archived'], 'active'),
    ...(can('projects.finance.read') ? [{ name: 'budget', label: 'Budget', type: 'number', default: 0 }] : []),
    { name: 'strategy', label: 'Strategy', type: 'textarea', colSpan: 2 },
  ],
})

export const ProgramsPage = makePage({
  eyebrow: 'Projects',
  title: 'Programs',
  description: 'Coordinated projects, benefits and programme-level ownership.',
  endpoint: '/projects/programs',
  permission: 'projects.program',
  createLabel: 'New program',
  filters: [{ name: 'status', label: 'All statuses', options: ['active', 'archived'] }],
  emptyIcon: Layers,
  columns: (can) => [
    { key: 'name', label: 'Program', render: (row) => <Primary title={row.name} subtitle={row.code} /> },
    refCol('portfolio_id', 'Portfolio', 'portfolios'),
    refCol('manager_employee_id', 'Manager', 'employees'),
    statusCol('health', 'Health'),
    statusCol(),
    ...(can('projects.finance.read') ? [{ key: 'benefits_json', label: 'Benefits', render: (row) => <span className="text-xs text-muted">{JSON.stringify(row.benefits_json ?? {})}</span> }] : []),
  ],
  fields: [
    { name: 'name', label: 'Program name', required: true },
    { name: 'code', label: 'Code', required: true },
    refField('portfolio_id', 'Portfolio', 'portfolios'),
    refField('manager_employee_id', 'Manager', 'employees'),
    selectField('health', 'Health', HEALTH, 'unknown'),
    selectField('status', 'Status', ['active', 'archived'], 'active'),
    { name: 'benefits_json', label: 'Benefits (JSON)', type: 'json', default: '{}', colSpan: 2 },
  ],
})

export const PhasesPage = makePage({
  eyebrow: 'Projects',
  title: 'Phases',
  description: 'Predictive delivery stages within a project plan.',
  endpoint: '/projects/phases',
  permission: 'projects.phase',
  createLabel: 'New phase',
  filters: [{ name: 'status', label: 'All statuses', options: ['planned', 'active', 'completed', 'cancelled'] }],
  emptyIcon: Layers,
  columns: [
    { key: 'name', label: 'Phase', render: (row) => <Primary title={row.name} subtitle={`Sequence ${row.sequence ?? '—'}`} /> },
    refCol('project_id', 'Project', 'projects'),
    qtyCol('sequence', 'Sequence'),
    dateCol('start_date', 'Starts'),
    dateCol('end_date', 'Ends'),
    statusCol(),
  ],
  fields: [
    refField('project_id', 'Project', 'projects', true),
    { name: 'name', label: 'Phase name', required: true },
    { name: 'sequence', label: 'Sequence', type: 'number', default: 1 },
    { name: 'start_date', label: 'Start date', type: 'date' },
    { name: 'end_date', label: 'End date', type: 'date' },
    selectField('status', 'Status', ['planned', 'active', 'completed', 'cancelled'], 'planned'),
  ],
})

export const TimeEntriesPage = makePage({
  eyebrow: 'Projects',
  title: 'Time entries',
  description: 'Auditable time logged against work items, with approval status.',
  endpoint: '/projects/time-entries',
  permission: 'projects.timeentry',
  createLabel: 'Log time',
  filters: [
    { name: 'status', label: 'All statuses', options: TIME_ENTRY_STATUSES },
    { name: 'entry_date', label: 'All dates', options: (rows) => [...new Set(rows.map((row) => row.entry_date).filter(Boolean))].map((value) => ({ value, label: dateLabel(value) })) },
  ],
  emptyIcon: Clock3,
  columns: (can) => [
    { key: 'work_item_id', label: 'Work item', render: (row) => <Ref lookup="workItems" id={row.work_item_id} /> },
    refCol('employee_id', 'Employee', 'employees'),
    dateCol('entry_date', 'Date'),
    qtyCol('hours', 'Hours'),
    { key: 'description', label: 'Description' },
    { key: 'billable', label: 'Billable', render: (row) => <Status value={row.billable ? 'active' : 'inactive'} /> },
    ...(can('projects.finance.read') ? [moneyCol('billable_rate', 'Rate')] : []),
    statusCol(),
  ],
  rowActions: (can) => [
    pmAction(can, {
      label: 'Submit',
      icon: Send,
      endpoint: (row) => `/projects/time-entries/${row.id}/submit`,
      body: () => ({ event: 'submit' }),
      permission: 'projects.timeentry.update',
      show: (row) => row.status === 'draft',
    }),
    pmAction(can, {
      label: 'Approve',
      icon: BadgeCheck,
      endpoint: (row) => `/projects/time-entries/${row.id}/approve`,
      body: () => ({}),
      permission: 'projects.timeentry.approve',
      tone: 'positive',
      show: (row) => row.status === 'submitted',
    }),
    pmAction(can, {
      label: 'Reject',
      icon: XCircle,
      endpoint: (row) => `/projects/time-entries/${row.id}/reject`,
      body: () => ({}),
      permission: 'projects.timeentry.approve',
      tone: 'danger',
      show: (row) => row.status === 'submitted',
    }),
  ],
  fields: [
    refField('work_item_id', 'Work item', 'workItems', true),
    refField('employee_id', 'Employee', 'employees'),
    { name: 'entry_date', label: 'Entry date', type: 'date', default: 'today', required: true },
    { name: 'hours', label: 'Hours', type: 'number', required: true },
    { name: 'billable', label: 'Billable', type: 'checkbox', default: true },
    selectField('source', 'Source', ['manual', 'import', 'timer', 'mobile'], 'manual'),
    { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
  ],
  canEdit: false,
})

export const TimesheetsPage = makePage({
  eyebrow: 'Projects',
  title: 'Timesheets',
  description: 'Weekly timesheet rollups with submission and manager approval.',
  endpoint: '/projects/timesheets',
  permission: 'projects.timesheet',
  createLabel: 'New timesheet',
  filters: [{ name: 'status', label: 'All statuses', options: TIMESHEET_STATUSES }],
  emptyIcon: CalendarDays,
  columns: (can) => [
    { key: 'week_start', label: 'Week', render: (row) => <Primary title={dateLabel(row.week_start)} subtitle={`${row.total_hours ?? 0} hours`} /> },
    refCol('employee_id', 'Employee', 'employees'),
    qtyCol('total_hours', 'Total hours'),
    ...(can('projects.finance.read') ? [qtyCol('billable_hours', 'Billable hours')] : []),
    statusCol(),
    dateCol('approved_at', 'Approved'),
  ],
  rowActions: (can) => [
    pmAction(can, {
      label: 'Submit',
      icon: Send,
      endpoint: (row) => `/projects/timesheets/${row.id}`,
      method: 'patch',
      body: () => ({ status: 'submitted' }),
      permission: 'projects.timesheet.update',
      show: (row) => row.status === 'draft' || row.status === 'rejected',
    }),
    pmAction(can, {
      label: 'Approve',
      icon: BadgeCheck,
      endpoint: (row) => `/projects/timesheets/${row.id}/approve`,
      body: () => ({}),
      permission: 'projects.timesheet.approve',
      tone: 'positive',
      show: (row) => row.status === 'submitted',
    }),
  ],
  fields: [
    refField('employee_id', 'Employee', 'employees', true),
    { name: 'week_start', label: 'Week starting', type: 'date', default: 'today', required: true },
    selectField('status', 'Status', TIMESHEET_STATUSES, 'draft'),
  ],
  canEdit: false,
})

export const ExpensesPage = makePage({
  eyebrow: 'Projects',
  title: 'Expenses',
  description: 'Project costs claimed by employees with billing status.',
  endpoint: '/projects/expenses',
  permission: 'projects.expense',
  createLabel: 'Record expense',
  filters: [
    { name: 'status', label: 'All statuses', options: EXPENSE_STATUSES },
    { name: 'category', label: 'All categories', options: EXPENSE_CATEGORIES },
  ],
  emptyIcon: Receipt,
  columns: (can) => [
    { key: 'category', label: 'Expense', render: (row) => <Primary title={titleCase(row.category)} subtitle={row.description || 'No description'} /> },
    refCol('project_id', 'Project', 'projects'),
    refCol('employee_id', 'Employee', 'employees'),
    ...(can('projects.finance.read') ? [moneyCol('amount', 'Amount'), moneyCol('tax_amount', 'Tax')] : []),
    { key: 'billable', label: 'Billable', render: (row) => <Status value={row.billable ? 'active' : 'inactive'} /> },
    statusCol(),
  ],
  fields: [
    refField('project_id', 'Project', 'projects', true),
    refField('work_item_id', 'Work item', 'workItems'),
    refField('employee_id', 'Employee', 'employees'),
    selectField('category', 'Category', EXPENSE_CATEGORIES, 'other'),
    { name: 'amount', label: 'Amount', type: 'number', required: true },
    { name: 'tax_amount', label: 'Tax amount', type: 'number', default: 0 },
    { name: 'billable', label: 'Billable', type: 'checkbox', default: true },
    { name: 'reimbursable', label: 'Reimbursable', type: 'checkbox', default: true },
    selectField('status', 'Status', EXPENSE_STATUSES, 'draft'),
  ],
})

export const CostEntriesPage = makePage({
  eyebrow: 'Projects',
  title: 'Cost ledger',
  description: 'Labour, expense, material and overhead costs posted to projects.',
  endpoint: '/projects/cost-entries',
  permission: 'projects.costentry',
  createLabel: 'Add cost entry',
  filters: [{ name: 'cost_type', label: 'All cost types', options: COST_TYPES }],
  emptyIcon: Wallet,
  columns: (can) => [
    { key: 'cost_type', label: 'Cost', render: (row) => <Primary title={titleCase(row.cost_type)} subtitle={row.source} /> },
    refCol('project_id', 'Project', 'projects'),
    refCol('work_item_id', 'Work item', 'workItems'),
    ...(can('projects.finance.read') ? [moneyCol('amount', 'Amount')] : []),
    dateCol('posted_at', 'Posted'),
  ],
  fields: [
    refField('project_id', 'Project', 'projects', true),
    refField('work_item_id', 'Work item', 'workItems'),
    selectField('cost_type', 'Cost type', COST_TYPES, 'labour'),
    { name: 'amount', label: 'Amount', type: 'number', required: true },
    { name: 'source', label: 'Source', default: 'manual' },
    { name: 'posted_at', label: 'Posted at', type: 'datetime', default: 'today' },
  ],
})

export const BillingRunsPage = makePage({
  eyebrow: 'Projects',
  title: 'Billing runs',
  description: 'Generate, review, approve and post invoice proposals to Finance.',
  endpoint: '/projects/billing-runs',
  permission: 'projects.billingrun',
  canCreate: false,
  filters: [
    { name: 'status', label: 'All statuses', options: BILLING_STATUSES },
    { name: 'period', label: 'All periods', options: (rows) => [...new Set(rows.map((row) => row.period).filter(Boolean))].map((value) => ({ value, label: value })) },
  ],
  headerActions: (
    <ActionDialog
      label="Generate billing run"
      icon={Receipt}
      permission="projects.billingrun.create"
      title="Generate billing run"
      description="Approved time, expenses and accepted milestones are included."
      endpoint="/projects/billing-runs"
      payload={(values) => ({ ...values, idempotency_key: crypto.randomUUID() })}
      fields={[
        refField('project_id', 'Project', 'projects', true),
        { name: 'period', label: 'Period', required: true, placeholder: '2026-11' },
        selectField('billing_type', 'Billing type', BILLING_TYPES, 'time_and_material'),
      ]}
    />
  ),
  emptyIcon: Receipt,
  columns: (can) => [
    { key: 'period', label: 'Period', render: (row) => <Primary title={row.period} subtitle={titleCase(row.billing_type)} /> },
    refCol('project_id', 'Project', 'projects'),
    ...(can('projects.finance.read') ? [moneyCol('gross_amount', 'Gross'), moneyCol('tax_amount', 'Tax')] : []),
    statusCol(),
    refCol('finance_invoice_id', 'Invoice', 'invoices'),
    dateCol('posted_at', 'Posted'),
  ],
  rowActions: (can) => [
    ...eventActions(
      can,
      (row) => `/projects/billing-runs/${row.id}/transition`,
      'projects.billingrun.update',
      [
        { event: 'generate', label: 'Generate lines', icon: ClipboardList, from: ['draft'] },
        { event: 'approve', label: 'Approve', icon: BadgeCheck, from: ['review'], tone: 'positive' },
        { event: 'retry', label: 'Retry', icon: RefreshCw, from: ['failed'] },
      ],
    ),
    pmAction(can, {
      label: 'Post to Finance',
      icon: Send,
      endpoint: (row) => `/projects/billing-runs/${row.id}/post`,
      body: () => ({}),
      permission: 'projects.billing.post',
      tone: 'positive',
      show: (row) => row.status === 'approved',
      success: 'Billing run posted',
    }),
  ],
  fields: (can) => [
    refField('project_id', 'Project', 'projects', true),
    { name: 'period', label: 'Period', required: true },
    selectField('status', 'Status', BILLING_STATUSES, 'draft'),
    ...(can('projects.finance.read') ? [{ name: 'gross_amount', label: 'Gross amount', type: 'number', default: 0 }] : []),
  ],
  canEdit: false,
})

export const BudgetsPage = makePage({
  eyebrow: 'Projects',
  title: 'Budgets',
  description: 'Versioned project budgets with approval and revision history.',
  endpoint: '/projects/budgets',
  permission: 'projects.budget',
  createLabel: 'New budget',
  filters: [{ name: 'status', label: 'All statuses', options: ['active', 'draft', 'approved', 'superseded'] }],
  emptyIcon: Wallet,
  columns: (can) => [
    { key: 'version', label: 'Budget', render: (row) => <Primary title={`Version ${row.version ?? 1}`} subtitle={titleCase(row.status)} /> },
    refCol('project_id', 'Project', 'projects'),
    ...(can('projects.finance.read')
      ? [qtyCol('budget_hours', 'Hours'), moneyCol('budget_cost', 'Cost'), moneyCol('budget_revenue', 'Revenue')]
      : []),
    dateCol('effective_from', 'Effective'),
    statusCol(),
  ],
  fields: (can) => [
    refField('project_id', 'Project', 'projects', true),
    { name: 'version', label: 'Version', type: 'number', default: 1 },
    ...(can('projects.finance.read')
      ? [
          { name: 'budget_hours', label: 'Budget hours', type: 'number', default: 0 },
          { name: 'budget_cost', label: 'Budget cost', type: 'number', default: 0 },
          { name: 'budget_revenue', label: 'Budget revenue', type: 'number', default: 0 },
        ]
      : []),
    { name: 'effective_from', label: 'Effective from', type: 'date' },
    selectField('status', 'Status', ['draft', 'active', 'approved', 'superseded'], 'active'),
  ],
})

export const ResourceRolesPage = makePage({
  eyebrow: 'Projects',
  title: 'Resource roles',
  description: 'Role catalogue used for bookings and rate cards.',
  endpoint: '/projects/resource-roles',
  permission: 'projects.resourcerole',
  createLabel: 'New role',
  emptyIcon: Users,
  columns: (can) => [
    { key: 'name', label: 'Role', render: (row) => <Primary title={row.name} subtitle={row.code} /> },
    ...(can('projects.finance.read') ? [moneyCol('default_cost_rate', 'Cost rate'), moneyCol('default_billable_rate', 'Billable rate')] : []),
    statusCol(),
  ],
  fields: (can) => [
    { name: 'code', label: 'Code', required: true },
    { name: 'name', label: 'Role name', required: true },
    ...(can('projects.finance.read')
      ? [
          { name: 'default_cost_rate', label: 'Default cost rate', type: 'number', default: 0 },
          { name: 'default_billable_rate', label: 'Default billable rate', type: 'number', default: 0 },
        ]
      : []),
    selectField('status', 'Status', ['active', 'inactive'], 'active'),
  ],
})

export const BookingsPage = makePage({
  eyebrow: 'Projects',
  title: 'Resource bookings',
  description: 'Capacity reservations against employees and project work.',
  endpoint: '/projects/bookings',
  permission: 'projects.booking',
  createLabel: 'Request booking',
  filters: [{ name: 'status', label: 'All statuses', options: BOOKING_STATUSES }],
  emptyIcon: Users,
  columns: [
    { key: 'project_id', label: 'Project', render: (row) => <Ref lookup="projects" id={row.project_id} /> },
    refCol('employee_id', 'Employee', 'employees'),
    refCol('work_item_id', 'Work item', 'workItems'),
    { key: 'role_code', label: 'Role' },
    dateCol('start_date', 'Starts'),
    dateCol('end_date', 'Ends'),
    qtyCol('allocation_percent', 'Allocation'),
    statusCol(),
  ],
  rowActions: (can) =>
    eventActions(
      can,
      (row) => `/projects/resource-bookings/${row.id}/approve`,
      'projects.resource.update',
      [
        { event: 'approve', label: 'Approve booking', icon: BadgeCheck, from: ['requested'], tone: 'positive' },
        { event: 'fulfill', label: 'Fulfil', icon: CheckCircle2, from: ['confirmed'], tone: 'positive' },
        { event: 'cancel', label: 'Cancel', icon: XCircle, from: ['requested', 'confirmed'], tone: 'danger' },
      ],
    ),
  fields: [
    refField('project_id', 'Project', 'projects', true),
    refField('employee_id', 'Employee', 'employees', true),
    refField('work_item_id', 'Work item', 'workItems'),
    { name: 'role_code', label: 'Role code' },
    { name: 'start_date', label: 'Start date', type: 'date', default: 'today', required: true },
    { name: 'end_date', label: 'End date', type: 'date', required: true },
    { name: 'hours_per_day', label: 'Hours per day', type: 'number', default: 8 },
    { name: 'allocation_percent', label: 'Allocation %', type: 'number', default: 100 },
    selectField('status', 'Status', BOOKING_STATUSES, 'requested'),
  ],
  canEdit: false,
})

export const CapacityPage = makePage({
  eyebrow: 'Projects',
  title: 'Capacity calendars',
  description: 'Leave-aware weekly capacity records sourced from HR or maintained manually.',
  endpoint: '/projects/capacity-calendars',
  permission: 'projects.capacitycalendar',
  createLabel: 'Add capacity',
  headerActions: (
    <ToolButton
      label="Refresh from HR"
      icon={RefreshCw}
      permission="projects.resource.update"
      endpoint="/projects/resources/capacity/refresh"
      success="Capacity refreshed"
      description="Leave and attendance data was reconciled for the current four weeks."
    />
  ),
  emptyIcon: CalendarDays,
  columns: [
    refCol('employee_id', 'Employee', 'employees'),
    dateCol('week_start', 'Week'),
    qtyCol('capacity_hours', 'Capacity'),
    qtyCol('planned_leave_hours', 'Leave'),
    qtyCol('holiday_hours', 'Holidays'),
    { key: 'source', label: 'Source', render: (row) => <TypeBadge value={row.source} /> },
    statusCol(),
  ],
  fields: [
    refField('employee_id', 'Employee', 'employees', true),
    { name: 'week_start', label: 'Week starting', type: 'date', default: 'today', required: true },
    { name: 'capacity_hours', label: 'Capacity hours', type: 'number', default: 40 },
    { name: 'planned_leave_hours', label: 'Planned leave hours', type: 'number', default: 0 },
    { name: 'holiday_hours', label: 'Holiday hours', type: 'number', default: 0 },
    selectField('source', 'Source', ['hr', 'manual'], 'hr'),
    selectField('status', 'Status', ['active', 'inactive'], 'active'),
  ],
})

export const WorkloadPage = makePage({
  eyebrow: 'Projects',
  title: 'Workload snapshots',
  description: 'Weekly utilisation and overallocation indicators by employee.',
  endpoint: '/projects/workload-snapshots',
  permission: 'projects.workload',
  canCreate: false,
  canEdit: false,
  canDelete: false,
  emptyIcon: BarChart3,
  columns: [
    refCol('employee_id', 'Employee', 'employees'),
    dateCol('week_start', 'Week'),
    qtyCol('booked_hours', 'Booked'),
    qtyCol('available_hours', 'Available'),
    { key: 'utilization_percent', label: 'Utilisation', render: (row) => pct(row.utilization_percent) },
    { key: 'overallocated', label: 'Overallocated', render: (row) => <Status value={row.overallocated ? 'escalated' : 'active'} /> },
  ],
  fields: [],
})

export const RisksPage = makePage({
  eyebrow: 'Projects',
  title: 'Risk register',
  description: 'Probability, impact, mitigation and escalation for project risks.',
  endpoint: '/projects/risks',
  permission: 'projects.risk',
  createLabel: 'Identify risk',
  filters: [{ name: 'status', label: 'All statuses', options: RISK_STATUSES }],
  emptyIcon: ShieldAlert,
  columns: [
    { key: 'title', label: 'Risk', render: (row) => <Primary title={row.title} subtitle={row.mitigation_plan || 'No mitigation plan'} /> },
    refCol('project_id', 'Project', 'projects'),
    qtyCol('probability', 'Probability'),
    qtyCol('impact', 'Impact'),
    qtyCol('score', 'Score'),
    refCol('owner_employee_id', 'Owner', 'employees'),
    statusCol(),
  ],
  rowActions: (can) =>
    eventActions(
      can,
      (row) => `/projects/risks/${row.id}/transition`,
      'projects.risk.update',
      [
        { event: 'assess', label: 'Assess', icon: ClipboardList, from: ['identified'] },
        { event: 'mitigate', label: 'Mitigate', icon: Check, from: ['analysing', 'escalated'], tone: 'positive' },
        { event: 'escalate', label: 'Escalate', icon: ShieldAlert, from: ['analysing'], tone: 'danger' },
        { event: 'close', label: 'Close', icon: LockKeyhole, from: ['analysing', 'mitigated', 'escalated'] },
        { event: 'reopen', label: 'Reopen', icon: RefreshCw, from: ['closed', 'mitigated'] },
      ],
    ),
  fields: [
    refField('project_id', 'Project', 'projects', true),
    { name: 'title', label: 'Risk title', required: true },
    { name: 'probability', label: 'Probability', type: 'number', default: 1 },
    { name: 'impact', label: 'Impact', type: 'number', default: 1 },
    refField('owner_employee_id', 'Owner', 'employees'),
    selectField('response_strategy', 'Response strategy', ['avoid', 'mitigate', 'transfer', 'accept'], 'mitigate'),
    { name: 'due_date', label: 'Due date', type: 'date' },
    selectField('status', 'Status', RISK_STATUSES, 'identified'),
    { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
    { name: 'mitigation_plan', label: 'Mitigation plan', type: 'textarea', colSpan: 2 },
  ],
  canEdit: false,
})

export const IssuesPage = makePage({
  eyebrow: 'Projects',
  title: 'Issues',
  description: 'Triage and resolution of delivery blockers and defects.',
  endpoint: '/projects/issues',
  permission: 'projects.issue',
  createLabel: 'Log issue',
  filters: [
    { name: 'status', label: 'All statuses', options: ISSUE_STATUSES },
    { name: 'severity', label: 'All severities', options: SEVERITIES },
  ],
  emptyIcon: Activity,
  columns: [
    { key: 'title', label: 'Issue', render: (row) => <Primary title={row.title} subtitle={row.description || 'No description'} /> },
    refCol('project_id', 'Project', 'projects'),
    refCol('work_item_id', 'Work item', 'workItems'),
    { key: 'severity', label: 'Severity', render: (row) => <TypeBadge value={row.severity} /> },
    refCol('owner_employee_id', 'Owner', 'employees'),
    statusCol(),
  ],
  rowActions: (can) =>
    eventActions(
      can,
      (row) => `/projects/issues/${row.id}/transition`,
      'projects.issue.update',
      [
        { event: 'triage', label: 'Triage', icon: ClipboardList, from: ['open'] },
        { event: 'start', label: 'Start', icon: Play, from: ['triaged'] },
        { event: 'resolve', label: 'Resolve', icon: CheckCircle2, from: ['in_progress'], tone: 'positive' },
        { event: 'close', label: 'Close', icon: LockKeyhole, from: ['resolved'] },
        { event: 'reopen', label: 'Reopen', icon: RefreshCw, from: ['resolved', 'closed'] },
      ],
    ),
  fields: [
    refField('project_id', 'Project', 'projects', true),
    { name: 'title', label: 'Issue title', required: true },
    refField('work_item_id', 'Work item', 'workItems'),
    refField('linked_risk_id', 'Linked risk', 'risks'),
    refField('owner_employee_id', 'Owner', 'employees'),
    selectField('severity', 'Severity', SEVERITIES, 'medium'),
    selectField('status', 'Status', ISSUE_STATUSES, 'open'),
    { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
  ],
  canEdit: false,
})

export const ChangeRequestsPage = makePage({
  eyebrow: 'Projects',
  title: 'Change requests',
  description: 'Scope, cost and schedule changes awaiting approval.',
  endpoint: '/projects/change-requests',
  permission: 'projects.changerequest',
  createLabel: 'New change request',
  filters: [{ name: 'status', label: 'All statuses', options: CHANGE_STATUSES }],
  emptyIcon: GitBranch,
  columns: (can) => [
    { key: 'title', label: 'Change', render: (row) => <Primary title={row.title} subtitle={row.reason || 'No reason recorded'} /> },
    refCol('project_id', 'Project', 'projects'),
    { key: 'scope_impact', label: 'Scope impact' },
    ...(can('projects.finance.read') ? [moneyCol('cost_impact', 'Cost impact')] : []),
    qtyCol('schedule_impact', 'Schedule impact'),
    statusCol(),
  ],
  rowActions: (can) =>
    eventActions(
      can,
      (row) => `/projects/change-requests/${row.id}/transition`,
      'projects.changerequest.update',
      [
        { event: 'submit', label: 'Submit', icon: Send, from: ['draft'] },
        { event: 'approve', label: 'Approve', icon: BadgeCheck, from: ['submitted'], tone: 'positive' },
        { event: 'reject', label: 'Reject', icon: XCircle, from: ['submitted'], tone: 'danger' },
        { event: 'apply', label: 'Apply', icon: CheckCircle2, from: ['approved'], tone: 'positive' },
      ],
    ),
  fields: (can) => [
    refField('project_id', 'Project', 'projects', true),
    { name: 'title', label: 'Title', required: true },
    { name: 'reason', label: 'Reason', type: 'textarea', colSpan: 2 },
    { name: 'scope_impact', label: 'Scope impact', type: 'textarea', colSpan: 2 },
    ...(can('projects.finance.read') ? [{ name: 'cost_impact', label: 'Cost impact', type: 'number', default: 0 }] : []),
    { name: 'schedule_impact', label: 'Schedule impact (days)', type: 'number', default: 0 },
    selectField('status', 'Status', CHANGE_STATUSES, 'draft'),
  ],
  canEdit: false,
})

export const DecisionsPage = makePage({
  eyebrow: 'Projects',
  title: 'Decision log',
  description: 'Recorded scope, cost and delivery decisions with owners.',
  endpoint: '/projects/decisions',
  permission: 'projects.decision',
  createLabel: 'Record decision',
  emptyIcon: BookOpen,
  columns: [
    { key: 'title', label: 'Decision', render: (row) => <Primary title={row.title} subtitle={row.decision || 'No decision recorded'} /> },
    refCol('project_id', 'Project', 'projects'),
    refCol('decided_by_id', 'Decided by', 'users'),
    dateCol('decided_at', 'Decided'),
    statusCol(),
  ],
  fields: [
    refField('project_id', 'Project', 'projects', true),
    { name: 'title', label: 'Title', required: true },
    { name: 'context', label: 'Context', type: 'textarea', colSpan: 2 },
    { name: 'decision', label: 'Decision', type: 'textarea', colSpan: 2 },
    selectField('status', 'Status', ['draft', 'recorded', 'superseded'], 'draft'),
  ],
  rowActions: (can) => [
    pmAction(can, {
      label: 'Publish decision',
      icon: Send,
      endpoint: (row) => `/projects/decisions/${row.id}`,
      method: 'patch',
      body: () => ({ status: 'recorded', decided_at: new Date().toISOString() }),
      permission: 'projects.decision.update',
      show: (row) => row.status === 'draft',
    }),
  ],
})

export const StatusUpdatesPage = makePage({
  eyebrow: 'Projects',
  title: 'Status updates',
  description: 'Health, achievements, blockers and next steps by reporting period.',
  endpoint: '/projects/status-updates',
  permission: 'projects.statusupdate',
  createLabel: 'New status update',
  filters: [
    { name: 'health', label: 'All health', options: HEALTH },
    { name: 'status', label: 'All statuses', options: ['draft', 'published', 'archived'] },
  ],
  emptyIcon: FileText,
  columns: [
    { key: 'period', label: 'Period', render: (row) => <Primary title={row.period} subtitle={row.summary || 'No summary'} /> },
    refCol('project_id', 'Project', 'projects'),
    statusCol('health', 'Health'),
    statusCol(),
    dateCol('published_at', 'Published'),
  ],
  rowActions: (can) => [
    pmAction(can, {
      label: 'Publish',
      icon: Send,
      endpoint: (row) => `/projects/status-updates/${row.id}`,
      method: 'patch',
      body: () => ({ status: 'published' }),
      permission: 'projects.statusupdate.update',
      tone: 'positive',
      show: (row) => row.status === 'draft',
    }),
  ],
  fields: [
    refField('project_id', 'Project', 'projects', true),
    { name: 'period', label: 'Period', required: true, placeholder: '2026-W46' },
    selectField('health', 'Health', HEALTH, 'unknown'),
    { name: 'summary', label: 'Summary', type: 'textarea', colSpan: 2 },
    { name: 'achievements', label: 'Achievements', type: 'textarea', colSpan: 2 },
    { name: 'blockers', label: 'Blockers', type: 'textarea', colSpan: 2 },
    { name: 'next_steps', label: 'Next steps', type: 'textarea', colSpan: 2 },
    selectField('status', 'Status', ['draft', 'published', 'archived'], 'draft'),
  ],
  canEdit: false,
})

export const GoalsPage = makePage({
  eyebrow: 'Projects',
  title: 'Goals & OKRs',
  description: 'Measurable outcomes linked to portfolios, programmes and projects.',
  endpoint: '/projects/goals',
  permission: 'projects.goal',
  createLabel: 'New goal',
  filters: [{ name: 'status', label: 'All statuses', options: GOAL_STATUSES }],
  emptyIcon: Target,
  columns: [
    { key: 'title', label: 'Goal', render: (row) => <Primary title={row.title} subtitle={row.metric || 'No metric'} /> },
    refCol('portfolio_id', 'Portfolio', 'portfolios'),
    refCol('program_id', 'Program', 'programs'),
    refCol('project_id', 'Project', 'projects'),
    qtyCol('target', 'Target'),
    qtyCol('current', 'Current'),
    statusCol(),
  ],
  fields: [
    { name: 'title', label: 'Goal title', required: true },
    refField('portfolio_id', 'Portfolio', 'portfolios'),
    refField('program_id', 'Program', 'programs'),
    refField('project_id', 'Project', 'projects'),
    { name: 'metric', label: 'Metric' },
    { name: 'target', label: 'Target', type: 'number', default: 0 },
    { name: 'current', label: 'Current', type: 'number', default: 0 },
    refField('owner_employee_id', 'Owner', 'employees'),
    selectField('status', 'Status', GOAL_STATUSES, 'active'),
  ],
})

export const AiSignalsPage = makePage({
  eyebrow: 'Projects',
  title: 'AI signals',
  description: 'Reviewed risk, schedule and cost signals with model provenance.',
  endpoint: '/projects/ai-signals',
  permission: 'projects.aisignal',
  canCreate: false,
  filters: [
    { name: 'review_status', label: 'All reviews', options: ['pending', 'reviewed'] },
    { name: 'signal_type', label: 'All signal types', options: ['delay_risk', 'budget_variance', 'blocked_work', 'scope_risk'] },
  ],
  headerActions: (
    <>
      <Link to="/projects/reports?report=ai_governance" className="btn-secondary">
        <BarChart3 size={15} /> AI governance report
      </Link>
      <ToolButton
        label="Refresh signals"
        icon={Sparkles}
        permission="projects.aisignal.update"
        endpoint="/projects/ai/signals/refresh"
        success="Signals refreshed"
        description="Project signals were recalculated from current delivery data."
      />
    </>
  ),
  emptyIcon: Sparkles,
  columns: [
    { key: 'signal_type', label: 'Signal', render: (row) => <Primary title={titleCase(row.signal_type)} subtitle={row.explanation || 'No explanation'} /> },
    { key: 'entity_type', label: 'Entity', render: (row) => <TypeBadge value={row.entity_type} /> },
    qtyCol('score', 'Score'),
    {
      key: 'features_json',
      label: 'Top 3 features',
      render: (row) => (
        <div className="flex flex-wrap gap-1">
          {topFeatures(row.features_json ?? row.features).map(([name, value]) => (
            <span key={name} className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-soft">
              {titleCase(name)}: {num(value, 2)}
            </span>
          ))}
        </div>
      ),
    },
    { key: 'model_version', label: 'Model version' },
    { key: 'generated_at', label: 'Generated at', render: (row) => <DateCell value={row.generated_at} time /> },
    statusCol('review_status', 'Review state'),
  ],
  rowActions: (can) => [
    pmAction(can, {
      label: 'Review signal',
      icon: BadgeCheck,
      endpoint: (row) => `/projects/ai/signals/${row.id}/review`,
      body: () => ({}),
      permission: 'projects.ai.review',
      tone: 'positive',
      show: (row) => row.review_status !== 'reviewed',
    }),
  ],
  fields: [],
  canEdit: false,
  canDelete: false,
})

export const AiActionsPage = makePage({
  eyebrow: 'Projects',
  title: 'AI actions',
  description: 'Human-approved AI proposals. Auto-close, auto-approve and auto-post are prohibited; execution is always an explicit human action.',
  endpoint: '/projects/ai-actions',
  permission: 'projects.aiaction',
  canCreate: false,
  filters: [
    { name: 'status', label: 'All statuses', options: AI_ACTION_STATUSES },
    { name: 'action_type', label: 'All action types', options: AI_ACTION_TYPES },
  ],
  headerActions: (
    <Link to="/projects/reports?report=ai_governance" className="btn-secondary">
      <BarChart3 size={15} /> AI governance report
    </Link>
  ),
  emptyIcon: Sparkles,
  columns: [
    { key: 'action_type', label: 'Action', render: (row) => <Primary title={titleCase(row.action_type)} subtitle={`${row.entity_type} · ${row.entity_id}`} /> },
    statusCol(),
    {
      key: 'proposed_json',
      label: 'Proposed JSON / scope',
      render: (row) => (
        <div className="max-w-xs">
          <p className="text-[10px] font-bold text-ink">Scope: {aiActionScope(row)}</p>
          <pre className="mt-1 max-h-16 overflow-auto whitespace-pre-wrap text-[10px] text-muted">
            {JSON.stringify(row.proposed_json ?? {}, null, 2)}
          </pre>
        </div>
      ),
    },
    refCol('requested_by_id', 'Requested by', 'users'),
    refCol('approved_by_id', 'Approver', 'users'),
    refCol('on_behalf_of_id', 'On behalf of', 'users'),
    {
      key: 'reversal_reference',
      label: 'Reversal reference',
      render: (row) => <span className="text-[11px] text-ink-soft">{row.reversal_reference ?? '—'}</span>,
    },
    {
      key: 'control',
      label: 'Control',
      render: (row) => <Status value={isProhibitedAiAction(row) ? 'blocked' : 'manual'} />,
    },
    { key: 'executed_at', label: 'Executed', render: (row) => <DateCell value={row.executed_at} time /> },
  ],
  rowActions: (can) => [
    pmAction(can, {
      label: 'Approve',
      icon: BadgeCheck,
      endpoint: (row) => `/projects/ai/actions/${row.id}/review`,
      body: () => ({}),
      permission: 'projects.ai.review',
      tone: 'positive',
      show: (row) => row.status === 'proposed',
    }),
    pmAction(can, {
      label: 'Reject',
      icon: XCircle,
      endpoint: (row) => `/projects/ai/actions/${row.id}/reject`,
      body: () => ({}),
      permission: 'projects.ai.review',
      tone: 'danger',
      show: (row) => row.status === 'proposed' || row.status === 'approved',
    }),
    pmAction(can, {
      label: 'Execute',
      icon: Zap,
      endpoint: (row) => `/projects/ai/actions/${row.id}/execute`,
      body: () => ({}),
      permission: 'projects.ai.execute',
      tone: 'positive',
      show: (row) => row.status === 'approved' && !isProhibitedAiAction(row),
    }),
    pmAction(can, {
      label: 'Reverse',
      icon: RotateCcw,
      endpoint: (row) => `/projects/ai/actions/${row.id}/reverse`,
      body: () => ({ reversal_reference: `ui:${crypto.randomUUID()}` }),
      permission: 'projects.ai.reverse',
      show: (row) => row.status === 'executed',
    }),
  ],
  fields: [],
  canEdit: false,
  canDelete: false,
})

export const AutomationRulesPage = makePage({
  eyebrow: 'Projects',
  title: 'Automation rules',
  description: 'Triggers, conditions and actions executed with the actor’s permissions.',
  endpoint: '/projects/automation-rules',
  permission: 'projects.automation',
  createLabel: 'New automation rule',
  filters: [{ name: 'status', label: 'All statuses', options: AUTOMATION_STATUSES }],
  emptyIcon: Workflow,
  columns: [
    { key: 'name', label: 'Rule', render: (row) => <Primary title={row.name} subtitle={JSON.stringify(row.trigger_json ?? {})} /> },
    refCol('project_id', 'Project', 'projects'),
    qtyCol('run_count', 'Runs'),
    statusCol(),
  ],
  rowActions: (can) => [
    pmAction(can, {
      label: 'Run rule',
      icon: Zap,
      endpoint: () => '/projects/automation/runs',
      body: (row) => ({ trigger_entity: 'automation_rule', trigger_id: row.id }),
      permission: 'projects.automation.run',
      success: 'Automation triggered',
      show: (row) => row.status === 'active',
    }),
  ],
  fields: [
    refField('project_id', 'Project', 'projects'),
    { name: 'name', label: 'Rule name', required: true },
    { name: 'trigger_json', label: 'Trigger (JSON)', type: 'json', default: '{"event":"work_item.created"}', colSpan: 2 },
    { name: 'conditions_json', label: 'Conditions (JSON)', type: 'json', default: '[]', colSpan: 2 },
    { name: 'actions_json', label: 'Actions (JSON)', type: 'json', default: '[]', colSpan: 2 },
    selectField('status', 'Status', AUTOMATION_STATUSES, 'active'),
  ],
})

export const AutomationRunsPage = makePage({
  eyebrow: 'Projects',
  title: 'Automation runs',
  description: 'Audit trail of automation executions and failures.',
  endpoint: '/projects/automation-runs',
  permission: 'projects.automationrun',
  canCreate: false,
  canEdit: false,
  canDelete: false,
  filters: [{ name: 'status', label: 'All statuses', options: ['pending', 'success', 'failed'] }],
  emptyIcon: Workflow,
  columns: [
    { key: 'trigger_entity', label: 'Trigger', render: (row) => <Primary title={titleCase(row.trigger_entity)} subtitle={row.trigger_id} /> },
    refCol('rule_id', 'Rule', 'automationRules'),
    statusCol(),
    { key: 'error', label: 'Error' },
    dateCol('started_at', 'Started'),
    dateCol('finished_at', 'Finished'),
  ],
  fields: [],
})

export const OutboxPage = makePage({
  eyebrow: 'Projects',
  title: 'Event outbox',
  description: 'Reliable cross-module events with pending, published and failed states.',
  endpoint: '/projects/outbox',
  permission: 'projects.outbox',
  canCreate: false,
  canEdit: false,
  canDelete: false,
  filters: [{ name: 'status', label: 'All statuses', options: OUTBOX_STATUSES }],
  headerActions: (
    <ToolButton
      label="Dispatch pending"
      icon={Send}
      permission="projects.outbox.dispatch"
      endpoint="/projects/outbox/dispatch"
      params={{ limit: 50 }}
      success="Dispatch complete"
      description="Pending project events were handed to the integration providers."
    />
  ),
  emptyIcon: Inbox,
  columns: [
    { key: 'event_name', label: 'Event', render: (row) => <Primary title={row.event_name} subtitle={row.error || 'No errors'} /> },
    statusCol(),
    qtyCol('attempts', 'Attempts'),
    dateCol('available_at', 'Available'),
    dateCol('published_at', 'Published'),
  ],
  fields: [],
})

function ColumnsIcon() {
  return <Layers size={24} strokeWidth={1.7} />
}

export { default as ReportsPage } from './projects-reports'

export function BoardPage() {
  const can = useCan()
  const [searchParams] = useSearchParams()
  const projectParam = searchParams.get('project_id') ?? ''
  const [boardId, setBoardId] = useState('')
  const [board, setBoard] = useState(null)
  const [columns, setColumns] = useState([])
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [dragging, setDragging] = useState(null)
  const [moving, setMoving] = useState(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [values, setValues] = useState({})

  useEffect(() => {
    let active = true
    fetchLookup('boards')
      .then((options) => {
        if (!active || !options.length) return
        const match = projectParam ? options.find((option) => option.raw?.project_id === projectParam) : null
        const next = match?.value ?? options[0].value
        setBoardId((current) => current || next)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [projectParam])

  const load = useCallback(async () => {
    if (!boardId) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const [boardResponse, columnResponse, itemResponse] = await Promise.all([
        api.get(`/projects/boards/${boardId}`),
        api.get('/projects/board-columns', { params: { board_id: boardId, size: 200 } }),
        api.get('/projects/work-items', { params: { board_id: boardId, size: 200 } }),
      ])
      const toRows = (data) => (Array.isArray(data) ? data : data.items ?? [])
      setBoard(boardResponse.data)
      setColumns(toRows(columnResponse.data).sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0)))
      setItems(toRows(itemResponse.data))
    } catch {
      setBoard(null)
      setColumns([])
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [boardId])

  useEffect(() => {
    load()
  }, [load])

  const actions = useMemo(
    () => eventActions(can, (row) => `/projects/work-items/${row.id}/transition`, 'projects.workitem.update', WORK_ITEM_EVENTS),
    [can],
  )

  const moveItem = async (item, column) => {
    if (!can('projects.workitem.update') || !column || item.board_column_id === column.id) return
    const occupantCount = items.filter((entry) => entry.board_column_id === column.id && entry.id !== item.id).length
    const enforced = Boolean(board?.wip_enabled && column.wip_enforced)
    if (column.wip_limit && occupantCount >= column.wip_limit && enforced) {
      toast.error('WIP limit reached', `${column.name} enforces a limit of ${column.wip_limit} items.`)
      return
    }
    const rank = Math.max(0, ...items.map((entry) => Number(entry.rank ?? 0))) + 10
    setMoving(item.id)
    try {
      await api.patch(`/projects/work-items/${item.id}`, { board_id: boardId, board_column_id: column.id })
      await api.patch(`/projects/work-items/${item.id}/rank`, null, { params: { rank } })
      toast.success('Work item moved', `${item.title} moved to ${column.name}.`)
      await load()
    } catch (error) {
      toast.error('Could not move item', apiErrorMessage(error))
    } finally {
      setMoving(null)
      setDragging(null)
    }
  }

  const openCreate = () => {
    setValues({
      project_id: board?.project_id ?? '',
      board_id: boardId,
      board_column_id: columns[0]?.id ?? '',
      title: '',
      work_item_type: 'task',
      status: 'todo',
      priority: 'medium',
    })
    setCreateOpen(true)
  }

  const submitCreate = async () => {
    if (!values.title || !values.board_column_id) {
      toast.error('Missing details', 'A title and board column are required.')
      return
    }
    setCreating(true)
    try {
      await api.post('/projects/work-items', values)
      toast.success('Work item created', 'The item was added to the selected column.')
      setCreateOpen(false)
      await load()
    } catch (error) {
      toast.error('Could not create work item', apiErrorMessage(error))
    } finally {
      setCreating(false)
    }
  }

  if (!can('projects.board.read')) {
    return <EmptyState title="You don’t have access to this area" description="Ask an administrator for project board access." />
  }

  const projectPath = board?.project_id ? `/projects/projects/${board.project_id}` : '/projects/projects'
  const backlogPath = board?.project_id ? `/projects/backlog?project_id=${board.project_id}` : '/projects/backlog'

  return (
    <>
      <PageHeader
        eyebrow="Projects"
        title="Board"
        description="Drag work items between columns or use the move control. WIP limits are advisory unless a column enforces them."
        actions={
          <>
            <Link to={backlogPath} className="btn-secondary">
              <ClipboardList size={15} /> Backlog
            </Link>
            <Link to={projectPath} className="btn-secondary">
              <FolderKanban size={15} /> Project
            </Link>
            <div className="w-full sm:w-64">
              <RemoteSelect lookup="boards" value={boardId} onChange={setBoardId} placeholder="Select a board" />
            </div>
            {can('projects.workitem.create') && (
              <button type="button" className="btn-primary" onClick={openCreate} disabled={!columns.length}>
                <Plus size={16} /> New work item
              </button>
            )}
          </>
        }
      />
      {board && (
        <p className="mb-4 text-xs text-muted">
          WIP limits are <span className="font-bold text-ink">{board.wip_enabled ? 'enforced per column setting' : 'advisory'}</span> on this board.
        </p>
      )}
      {loading ? (
        <div className="card flex justify-center py-20">
          <Spinner />
        </div>
      ) : columns.length === 0 ? (
        <EmptyState icon={Layers} title="No board columns" description="Add columns to a board before planning work on it." />
      ) : (
        <div className="flex gap-4 overflow-x-auto pb-4">
          {columns.map((column) => {
            const cardItems = items.filter((item) => item.board_column_id === column.id)
            const enforced = Boolean(board?.wip_enabled && column.wip_enforced)
            const overLimit = column.wip_limit != null && cardItems.length > column.wip_limit
            return (
              <div
                key={column.id}
                className="card w-72 shrink-0 p-3"
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault()
                  const item = items.find((entry) => entry.id === dragging)
                  if (item) moveItem(item, column)
                }}
              >
                <div className="mb-3 flex items-start justify-between gap-2 border-b border-line pb-3">
                  <div>
                    <p className="text-sm font-bold text-ink">{column.name}</p>
                    <p className="text-[11px] text-muted">
                      {titleCase(column.status_category)} · {cardItems.length}
                      {column.wip_limit != null ? ` / ${column.wip_limit}` : ''} items
                    </p>
                    {column.wip_limit != null && (
                      <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
                        {enforced ? 'WIP enforced' : 'WIP advisory'}
                      </p>
                    )}
                  </div>
                  {column.wip_limit != null && (
                    <Status value={overLimit ? (enforced ? 'blocked' : 'escalated') : 'active'} />
                  )}
                </div>
                <div className="space-y-2">
                  {cardItems.length === 0 && <p className="py-6 text-center text-xs text-muted">Drop work items here</p>}
                  {cardItems.map((item) => (
                    <div
                      key={item.id}
                      draggable={can('projects.workitem.update')}
                      onDragStart={() => setDragging(item.id)}
                      onDragEnd={() => setDragging(null)}
                      className={`rounded-xl border border-line bg-surface-2 p-3 ${moving === item.id ? 'opacity-50' : ''}`}
                    >
                      <Primary title={item.title} subtitle={`${item.number ?? ''} · ${titleCase(item.work_item_type)} · rank ${num(item.rank, 0)}`} />
                      <div className="mt-2 flex items-center gap-2">
                        <Status value={item.status} />
                        {item.employee_id && <Ref lookup="employees" id={item.employee_id} />}
                      </div>
                      {can('projects.workitem.update') && (
                        <select
                          className="input mt-2 py-1.5 text-[11px]"
                          value={column.id}
                          onChange={(event) => {
                            const target = columns.find((entry) => entry.id === event.target.value)
                            moveItem(item, target)
                          }}
                        >
                          {columns.map((option) => (
                            <option key={option.id} value={option.id}>Move to {option.name}</option>
                          ))}
                        </select>
                      )}
                      <div className="mt-2 flex flex-wrap gap-1">
                        {actions
                          .filter((action) => !action.show || action.show(item))
                          .slice(0, 4)
                          .map((action) => {
                            const Icon = action.icon
                            return (
                              <button
                                key={action.label}
                                type="button"
                                title={action.label}
                                className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-muted transition hover:bg-surface hover:text-ink"
                                onClick={() => action.onClick(item, { reload: load })}
                              >
                                <Icon size={14} />
                              </button>
                            )
                          })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}
      <Modal
        open={createOpen}
        onClose={() => !creating && setCreateOpen(false)}
        title="New work item"
        description="The board and starting column are set automatically."
        size="md"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setCreateOpen(false)} disabled={creating}>Cancel</button>
            <button type="button" className="btn-primary" onClick={submitCreate} disabled={creating}>
              {creating && <Spinner className="h-4 w-4" />} Create work item
            </button>
          </>
        }
      >
        <FormGrid
          fields={[
            { name: 'title', label: 'Title', required: true },
            refField('project_id', 'Project', 'projects', true),
            selectField('work_item_type', 'Type', ['epic', 'feature', 'story', 'task', 'bug', 'enabler', 'subtask'], 'task'),
            selectField('status', 'Status', ['backlog', 'todo', 'in_progress', 'blocked', 'in_review', 'done'], 'todo'),
            selectField('priority', 'Priority', ['low', 'medium', 'high', 'urgent'], 'medium'),
            refField('board_column_id', 'Board column', 'boardColumns', true),
          ]}
          values={values}
          onChange={(name, value) => setValues((current) => ({ ...current, [name]: value }))}
        />
      </Modal>
    </>
  )
}
