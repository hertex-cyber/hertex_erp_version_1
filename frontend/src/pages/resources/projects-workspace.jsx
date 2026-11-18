import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowDown,
  ArrowUp,
  BadgeCheck,
  Ban,
  BarChart3,
  CheckCircle2,
  ClipboardList,
  FileText,
  FolderKanban,
  GitBranch,
  Layers,
  Play,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  Upload,
  Wallet,
} from 'lucide-react'
import { DataTable } from '../../components/DataTable'
import { FormGrid, RemoteSelect } from '../../components/Form'
import { EmptyState, KpiCard, Modal, PageHeader, SectionCard, Spinner } from '../../components/ui'
import { DateCell, Money, Primary, Ref, Status } from '../../components/cells'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel, money, num, titleCase } from '../../lib/format'
import { fetchLookup } from '../../lib/lookups'
import { toast } from '../../store/toast'
import { ActionDialog, ToolButton, refField, useCan } from './projects'

const toRows = (data) => (Array.isArray(data) ? data : data?.items ?? [])

function useProjectOptions() {
  const [options, setOptions] = useState([])
  useEffect(() => {
    let active = true
    fetchLookup('projects')
      .then((items) => active && setOptions(items))
      .catch(() => active && setOptions([]))
    return () => {
      active = false
    }
  }, [])
  return options
}

function ProjectPicker({ value, onChange, options, label = 'Project' }) {
  return (
    <div className="w-full sm:w-80">
      <label className="label">{label}</label>
      <select className="input" value={value ?? ''} onChange={(event) => onChange(event.target.value)}>
        <option value="">Select a project…</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </div>
  )
}

function DetailRow({ label, children }) {
  return (
    <div className="flex flex-col gap-1 border-b border-line/70 py-3 last:border-0 sm:flex-row sm:items-center sm:justify-between">
      <span className="text-[11px] font-bold uppercase tracking-[0.1em] text-muted">{label}</span>
      <span className="text-sm font-semibold text-ink">{children ?? '—'}</span>
    </div>
  )
}

function parseJson(text, label) {
  try {
    return JSON.parse(text || '{}')
  } catch {
    toast.error(`Invalid ${label}`, 'Enter valid JSON before continuing.')
    return null
  }
}

function asObject(value) {
  if (!value) return {}
  if (typeof value === 'string') {
    try {
      return JSON.parse(value) ?? {}
    } catch {
      return {}
    }
  }
  return value
}

export function ProjectDetailPage() {
  const { id } = useParams()
  const can = useCan()
  const [project, setProject] = useState(null)
  const [summary, setSummary] = useState(null)
  const [activity, setActivity] = useState([])
  const [comments, setComments] = useState([])
  const [attachments, setAttachments] = useState([])
  const [loading, setLoading] = useState(true)
  const [healthOpen, setHealthOpen] = useState(false)
  const [healthValues, setHealthValues] = useState({ health: 'green', health_reason: '' })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [projectResponse, summaryResponse, activityResponse, commentResponse, attachmentResponse] = await Promise.all([
        api.get(`/projects/${id}`),
        api.get(`/projects/projects/${id}/summary`).catch(() => null),
        api.get('/projects/activities', { params: { entity_type: 'project', entity_id: id, size: 5 } }).catch(() => null),
        api.get('/projects/comments', { params: { entity_type: 'project', entity_id: id, size: 5 } }).catch(() => null),
        api.get('/projects/attachments', { params: { entity_type: 'project', entity_id: id, size: 5 } }).catch(() => null),
      ])
      setProject(projectResponse.data)
      setSummary(summaryResponse?.data ?? null)
      setActivity(toRows(activityResponse?.data))
      setComments(toRows(commentResponse?.data))
      setAttachments(toRows(attachmentResponse?.data))
      setHealthValues({ health: projectResponse.data.health ?? 'green', health_reason: projectResponse.data.health_reason ?? '' })
    } catch (error) {
      toast.error('Could not load project', apiErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const saveHealth = async () => {
    try {
      await api.patch(`/projects/projects/${id}/health`, healthValues)
      toast.success('Health updated', 'Project health and reason were saved.')
      setHealthOpen(false)
      await load()
    } catch (error) {
      toast.error('Could not update health', apiErrorMessage(error))
    }
  }

  const lifecycle = [
    { key: 'submit', label: 'Submit for approval', icon: Send, event: 'submit', permission: 'projects.project.update' },
    { key: 'approve', label: 'Approve', icon: BadgeCheck, event: 'approve', permission: 'projects.approval.create' },
    { key: 'activate', label: 'Activate', icon: Play, event: 'activate', permission: 'projects.project.update' },
    { key: 'hold', label: 'Put on hold', icon: Ban, event: 'hold', permission: 'projects.project.update', reason: true },
    { key: 'cancel', label: 'Cancel', icon: Ban, event: 'cancel', permission: 'projects.project.update', reason: true, tone: 'danger' },
    { key: 'complete', label: 'Complete', icon: CheckCircle2, event: 'complete', permission: 'projects.project.update', reason: true },
  ]

  if (loading) return <div className="card flex justify-center py-20"><Spinner /></div>
  if (!project) return <EmptyState icon={FolderKanban} title="Project not found" description="This project may have been archived or is outside your access." />

  const base = `/projects/projects/${id}`
  const links = [
    { to: `/projects/backlog?project_id=${id}`, label: 'Backlog', icon: ClipboardList, hint: 'Rank, sprint and column planning' },
    { to: `/projects/board?project_id=${id}`, label: 'Board', icon: Layers, hint: 'Visual workflow with WIP controls' },
    { to: `/projects/gantt?project_id=${id}`, label: 'Gantt & baselines', icon: BarChart3, hint: 'Dependencies, critical path and variance' },
    { to: `/projects/tasks?project_id=${id}`, label: 'Tasks', icon: FolderKanban, hint: 'Delivery task register' },
    { to: `/projects/risks?project_id=${id}`, label: 'Risks', icon: ShieldAlert, hint: 'Risk register' },
    { to: `/projects/change-requests?project_id=${id}`, label: 'Change requests', icon: GitBranch, hint: 'Scope and baseline changes' },
    { to: `/projects/billing-runs?project_id=${id}`, label: 'Billing', icon: Wallet, hint: 'Billing runs and invoice links' },
    { to: `/projects/reports?project_id=${id}`, label: 'Profitability', icon: BarChart3, hint: 'Budget, billed revenue, WIP and margin' },
    { to: `/projects/reports?project_id=${id}&report=ai_governance`, label: 'AI governance', icon: Sparkles, hint: 'Signals, review state and reversals' },
    { to: `/projects/comments?project_id=${id}`, label: 'Comments', icon: FileText, hint: 'Discussion and decisions' },
  ]

  return (
    <>
      <PageHeader
        eyebrow={`Projects · ${project.code ?? ''}`}
        title={project.name}
        description={project.description || 'Project workspace, delivery controls and linked records.'}
        actions={
          <>
            {lifecycle
              .filter((action) => !action.reason)
              .map((action) => (
                <ToolButton
                  key={action.key}
                  label={action.label}
                  icon={action.icon}
                  permission={action.permission}
                  endpoint={`${base}/${action.key}`}
                  body={{ event: action.event }}
                  onDone={load}
                />
              ))}
            {lifecycle
              .filter((action) => action.reason)
              .map((action) => (
                <ActionDialog
                  key={action.key}
                  label={action.label}
                  icon={action.icon}
                  permission={action.permission}
                  title={action.label}
                  description={action.key === 'cancel' ? 'Cancellation requires an approved cancellation record.' : 'Add a comment for the audit trail.'}
                  fields={[{ name: 'comment', label: 'Comment', type: 'textarea', required: true }]}
                  endpoint={`${base}/${action.key}`}
                  payload={(values) => ({ event: action.event, comment: values.comment })}
                  success={action.label}
                  onDone={load}
                />
              ))}
            {can('projects.project.update') && (
              <button type="button" className="btn-secondary" onClick={() => setHealthOpen(true)}>
                <ShieldAlert size={15} /> Update health
              </button>
            )}
            <button type="button" className="btn-secondary" onClick={load}><RefreshCw size={15} /> Refresh</button>
          </>
        }
      >
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Status value={project.status} />
          <Status value={project.health} />
          {project.priority && <span className="badge">{titleCase(project.priority)} priority</span>}
        </div>
      </PageHeader>

      <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Tasks" value={num(summary?.total_tasks ?? 0)} hint={`${num(summary?.done_tasks ?? 0)} done`} icon={FolderKanban} />
        <KpiCard label="Open work" value={num(summary?.open_tasks ?? 0)} hint="Requires attention" icon={ClipboardList} tone="gold" />
        <KpiCard label="Hours" value={num(summary?.actual_hours ?? 0, 1)} hint={`of ${num(summary?.estimated_hours ?? 0, 1)} estimated`} icon={BarChart3} tone="sky" />
        {can('projects.finance.read') && (
          <KpiCard
            label="Budget"
            value={money(summary?.total_budget ?? project.budget, { currency: project.currency, restricted: true })}
            hint={`${money(summary?.billable_value ?? 0, { currency: project.currency, restricted: true })} billable`}
            icon={Wallet}
            tone="accent"
          />
        )}
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <SectionCard title="Project details" description="Master data is linked from existing registers." bodyClassName="p-5">
          <DetailRow label="Code">{project.code}</DetailRow>
          <DetailRow label="Status"><Status value={project.status} /></DetailRow>
          <DetailRow label="Health"><Status value={project.health} /></DetailRow>
          {project.health_reason && <DetailRow label="Health reason">{project.health_reason}</DetailRow>}
          <DetailRow label="Billing type">{titleCase(project.billing_type)}</DetailRow>
          <DetailRow label="Methodology">{titleCase(project.methodology)}</DetailRow>
          <DetailRow label="Manager"><Ref lookup="employees" id={project.manager_employee_id ?? project.project_manager_id} /></DetailRow>
          <DetailRow label="Customer"><Ref lookup="customers" id={project.customer_id} /></DetailRow>
          <DetailRow label="Start"><DateCell value={project.start_date} /></DetailRow>
        <DetailRow label="End"><DateCell value={project.end_date} /></DetailRow>
        {can('projects.finance.read') && <DetailRow label="Budget"><Money value={project.budget} currency={project.currency} restricted /></DetailRow>}
      </SectionCard>

        <SectionCard title="Workspace links" description="Open a linked register filtered to this project." bodyClassName="grid gap-2 p-5">
          {links.map((link) => {
            const Icon = link.icon
            return (
              <Link key={link.to} to={link.to} className="flex items-center gap-3 rounded-xl border border-line p-3 transition hover:bg-surface-2">
                <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary"><Icon size={16} /></span>
                <span>
                  <span className="block text-sm font-bold text-ink">{link.label}</span>
                  <span className="block text-[11px] text-muted">{link.hint}</span>
                </span>
              </Link>
            )
          })}
        </SectionCard>

        <div className="space-y-5">
          <SectionCard title="Recent activity" bodyClassName="divide-y divide-line/70">
            {activity.length === 0 ? <p className="p-5 text-xs text-muted">No activity recorded yet.</p> : activity.map((item) => (
              <div key={item.id} className="px-5 py-3">
                <p className="text-xs font-bold text-ink">{titleCase(item.action)}</p>
                <p className="mt-0.5 text-[11px] text-muted">{dateLabel(item.created_at)} · {item.actor_employee_id ?? 'System'}</p>
              </div>
            ))}
          </SectionCard>
          <SectionCard title="Comments" bodyClassName="divide-y divide-line/70">
            {comments.length === 0 ? <p className="p-5 text-xs text-muted">No comments yet.</p> : comments.map((item) => (
              <div key={item.id} className="px-5 py-3">
                <p className="line-clamp-2 text-xs text-ink-soft">{item.body}</p>
                <p className="mt-0.5 text-[11px] text-muted">{dateLabel(item.created_at)}</p>
              </div>
            ))}
          </SectionCard>
          <SectionCard title="Attachments" bodyClassName="divide-y divide-line/70">
            {attachments.length === 0 ? <p className="p-5 text-xs text-muted">No linked documents.</p> : attachments.map((item) => (
              <div key={item.id} className="px-5 py-3 text-xs text-ink-soft">
                {item.title ?? item.document_id} <span className="ml-1 text-[10px] font-bold uppercase text-muted">Documents ID</span>
              </div>
            ))}
          </SectionCard>
        </div>
      </div>

      <Modal
        open={healthOpen}
        onClose={() => setHealthOpen(false)}
        title="Update project health"
        description="Amber and red health should include a reason."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setHealthOpen(false)}>Cancel</button>
            <button type="button" className="btn-primary" onClick={saveHealth}>Save health</button>
          </>
        }
      >
        <FormGrid
          fields={[
            { name: 'health', label: 'Health', type: 'select', options: ['green', 'amber', 'red', 'unknown'], required: true },
            { name: 'health_reason', label: 'Reason', type: 'textarea' },
          ]}
          values={healthValues}
          onChange={(name, value) => setHealthValues((current) => ({ ...current, [name]: value }))}
        />
      </Modal>
    </>
  )
}

export function BacklogPage() {
  const can = useCan()
  const [searchParams] = useSearchParams()
  const projects = useProjectOptions()
  const [projectId, setProjectId] = useState(searchParams.get('project_id') ?? '')
  const [items, setItems] = useState([])
  const [sprints, setSprints] = useState([])
  const [columns, setColumns] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    if (!projectId) {
      setItems([])
      return
    }
    setLoading(true)
    try {
      const [backlogResponse, sprintResponse, columnResponse] = await Promise.all([
        api.get(`/projects/${projectId}/backlog`),
        api.get('/projects/sprints', { params: { project_id: projectId, size: 200 } }).catch(() => null),
        api.get('/projects/board-columns', { params: { size: 200 } }).catch(() => null),
      ])
      setItems(toRows(backlogResponse.data).map((row) => ({
        ...row,
        original_sprint_id: row.sprint_id,
        original_board_column_id: row.board_column_id,
        __dirty: false,
      })))
      setSprints(toRows(sprintResponse?.data))
      setColumns(toRows(columnResponse?.data).filter((column) => column.project_id === projectId || !column.project_id))
    } catch (error) {
      toast.error('Could not load backlog', apiErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    if (!projectId && projects.length) setProjectId(projects[0].value)
  }, [projectId, projects])

  useEffect(() => {
    load()
  }, [load])

  const updateRow = (id, changes) => {
    setItems((current) => current.map((row) => (row.id === id ? { ...row, ...changes, __dirty: true } : row)))
  }

  const reorder = async (index, direction) => {
    const sorted = [...items].sort((a, b) => Number(a.rank ?? 0) - Number(b.rank ?? 0))
    const target = index + direction
    if (target < 0 || target >= sorted.length) return
    const current = sorted[index]
    const neighbour = sorted[target]
    const currentRank = Number(current.rank ?? index * 1000)
    const neighbourRank = Number(neighbour.rank ?? target * 1000)
    const nextRank = direction < 0 ? (neighbourRank - 1) / 2 : (currentRank + neighbourRank) / 2
    if (!can('projects.workitem.update')) {
      toast.error('Not allowed', 'You need work item update access to reorder the backlog.')
      return
    }
    setSaving(true)
    try {
      await api.patch(`/projects/work-items/${current.id}/rank`, null, { params: { rank: nextRank } })
      toast.success('Rank updated', `${current.title} moved ${direction < 0 ? 'up' : 'down'}.`)
      await load()
    } catch (error) {
      toast.error('Could not update rank', apiErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const saveBacklog = async () => {
    const moves = items
      .filter((row) => row.__dirty)
      .map((row) => {
        const move = { work_item_id: row.id, rank: Number(row.rank ?? 0) }
        if ('sprint_id' in row && row.sprint_id !== row.original_sprint_id) move.sprint_id = row.sprint_id || null
        if ('board_column_id' in row && row.board_column_id !== row.original_board_column_id) {
          move.board_column_id = row.board_column_id || null
        }
        return move
      })
    if (!moves.length) {
      toast.info('No changes', 'Edit a rank, sprint or column first.')
      return
    }
    setSaving(true)
    try {
      await api.patch(`/projects/${projectId}/backlog`, { moves })
      toast.success('Backlog saved', `${moves.length} work item${moves.length === 1 ? '' : 's'} updated.`)
      await load()
    } catch (error) {
      toast.error('Could not save backlog', apiErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const sorted = useMemo(() => [...items].sort((a, b) => Number(a.rank ?? 0) - Number(b.rank ?? 0)), [items])
  const projectPath = projectId ? `/projects/projects/${projectId}` : '/projects/projects'
  const boardPath = projectId ? `/projects/board?project_id=${projectId}` : '/projects/board'

  return (
    <>
      <PageHeader
        eyebrow="Projects"
        title="Backlog"
        description="Reorder work items, assign sprints and set the starting board column."
        actions={
          <>
            <Link to={projectPath} className="btn-secondary"><FolderKanban size={15} /> Project</Link>
            <Link to={boardPath} className="btn-secondary"><Layers size={15} /> Board</Link>
            <button type="button" className="btn-primary" onClick={saveBacklog} disabled={saving || !items.some((item) => item.__dirty)}>
              {saving && <Spinner className="h-4 w-4" />} Save backlog
            </button>
          </>
        }
      />
      <div className="mb-5"><ProjectPicker value={projectId} onChange={setProjectId} options={projects} /></div>
      <div className="card overflow-hidden">
        <DataTable
          loading={loading}
          columns={[
            { key: 'rank', label: 'Rank', render: (row) => (
              <input
                className="input w-24 py-1.5 text-xs"
                type="number"
                value={row.rank ?? ''}
                onChange={(event) => updateRow(row.id, { rank: Number(event.target.value) })}
              />
            ) },
            { key: 'title', label: 'Work item', render: (row) => <Primary title={row.title} subtitle={`${row.number ?? ''} · ${titleCase(row.work_item_type)}`} /> },
            { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
            { key: 'sprint_id', label: 'Sprint', render: (row) => (
              <select className="input py-1.5 text-xs" value={row.sprint_id ?? ''} onChange={(event) => updateRow(row.id, { sprint_id: event.target.value || null })}>
                <option value="">Unassigned</option>
                {sprints.map((sprint) => <option key={sprint.id} value={sprint.id}>{sprint.name}</option>)}
              </select>
            ) },
            { key: 'board_column_id', label: 'Board column', render: (row) => (
              <select className="input py-1.5 text-xs" value={row.board_column_id ?? ''} onChange={(event) => updateRow(row.id, { board_column_id: event.target.value || null })}>
                <option value="">No column</option>
                {columns.map((column) => <option key={column.id} value={column.id}>{column.name}</option>)}
              </select>
            ) },
            { key: 'story_points', label: 'Points', align: 'right', render: (row) => <span className="font-bold text-ink">{num(row.story_points, 1)}</span> },
          ]}
          rows={sorted}
          rowKey={(row) => row.id}
          empty={<EmptyState icon={ClipboardList} title="No backlog items" description="Add work items to see them here." />}
          rowActions={(row) => {
            const index = sorted.findIndex((item) => item.id === row.id)
            return (
              <>
                <button type="button" title="Move up" className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink" onClick={() => reorder(index, -1)}>
                  <ArrowUp size={15} />
                </button>
                <button type="button" title="Move down" className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink" onClick={() => reorder(index, 1)}>
                  <ArrowDown size={15} />
                </button>
              </>
            )
          }}
        />
      </div>
    </>
  )
}

export function GanttPage() {
  const can = useCan()
  const [searchParams] = useSearchParams()
  const projects = useProjectOptions()
  const [projectId, setProjectId] = useState(searchParams.get('project_id') ?? '')
  const [data, setData] = useState(null)
  const [critical, setCritical] = useState(null)
  const [variance, setVariance] = useState([])
  const [loading, setLoading] = useState(false)
  const [baselineOpen, setBaselineOpen] = useState(false)
  const [baselineValues, setBaselineValues] = useState({ name: '', change_request_id: '', approval_id: '', comment: '' })

  const load = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const [ganttResponse, criticalResponse, varianceResponse] = await Promise.all([
        api.get(`/projects/projects/${projectId}/gantt`),
        api.get(`/projects/projects/${projectId}/critical-path`).catch(() => null),
        api.get(`/projects/projects/${projectId}/schedule-variance`).catch(() => null),
      ])
      setData(ganttResponse.data)
      setCritical(criticalResponse?.data ?? null)
      setVariance(toRows(varianceResponse?.data))
    } catch (error) {
      toast.error('Could not load schedule', apiErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    if (!projectId && projects.length) setProjectId(projects[0].value)
  }, [projectId, projects])

  useEffect(() => {
    load()
  }, [load])

  const scale = useMemo(() => {
    const tasks = data?.tasks ?? []
    if (!tasks.length) return { start: null, days: 1 }
    const times = tasks.flatMap((task) => [new Date(task.scheduled_start).getTime(), new Date(task.scheduled_end).getTime()])
    const start = new Date(Math.min(...times))
    const end = new Date(Math.max(...times))
    const days = Math.max(1, Math.round((end - start) / 86400000) + 1)
    return { start, days }
  }, [data])

  const position = (task) => {
    if (!scale.start) return { left: 0, width: 100 }
    const offset = Math.round((new Date(task.scheduled_start) - scale.start) / 86400000)
    return {
      left: (offset / scale.days) * 100,
      width: Math.max((Number(task.duration_days ?? 1) / scale.days) * 100, 1.5),
    }
  }

  const saveBaseline = async () => {
    if (baselineValues.name.trim().length < 2) {
      toast.error('Name required', 'Enter at least two characters for the baseline name.')
      return
    }
    try {
      await api.post(`/projects/projects/${projectId}/baselines`, {
        name: baselineValues.name,
        change_request_id: baselineValues.change_request_id || null,
        approval_id: baselineValues.approval_id || null,
        comment: baselineValues.comment || null,
      })
      toast.success('Baseline created', 'The approved schedule was snapshotted.')
      setBaselineOpen(false)
      setBaselineValues({ name: '', change_request_id: '', approval_id: '', comment: '' })
      await load()
    } catch (error) {
      toast.error('Could not create baseline', apiErrorMessage(error))
    }
  }

  const dependencyTitles = useMemo(() => {
    const map = {}
    for (const task of data?.tasks ?? []) map[task.work_item_id] = task.title
    return map
  }, [data])

  return (
    <>
      <PageHeader
        eyebrow="Projects"
        title="Gantt & baselines"
        description="Dependency-aware schedule, critical path, approved baselines and variance."
        actions={
          <>
            <Link to={projectId ? `/projects/projects/${projectId}` : '/projects/projects'} className="btn-secondary"><FolderKanban size={15} /> Project</Link>
            {can('projects.schedule.update') && (
              <button type="button" className="btn-primary" onClick={() => setBaselineOpen(true)} disabled={!projectId}>Create baseline</button>
            )}
          </>
        }
      />
      <div className="mb-5"><ProjectPicker value={projectId} onChange={setProjectId} options={projects} /></div>

      {loading ? (
        <div className="card flex justify-center py-20"><Spinner /></div>
      ) : !data?.tasks?.length ? (
        <EmptyState icon={BarChart3} title="No scheduled work" description="Add start and due dates to work items to build the schedule." />
      ) : (
        <div className="space-y-5">
          <SectionCard title="Schedule" description="Bars show dependency-adjusted dates. Critical items are highlighted.">
            <div className="overflow-x-auto">
              <div className="min-w-[900px] px-5 py-4">
                <div className="mb-3 flex items-center justify-between text-[11px] font-bold uppercase tracking-[0.1em] text-muted">
                  <span>{dateLabel(scale.start)}</span>
                  <span>{scale.days} day schedule</span>
                </div>
                {data.tasks.map((task) => {
                  const bar = position(task)
                  const shifted = task.start_date && task.scheduled_start !== task.start_date
                  return (
                    <div key={task.work_item_id} className="mb-2 grid grid-cols-[230px_1fr] items-center gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-xs font-bold text-ink">{task.title}</p>
                        <p className="text-[10px] text-muted">{dateLabel(task.scheduled_start)} → {dateLabel(task.scheduled_end)}</p>
                      </div>
                      <div className="relative h-7 rounded-lg bg-surface-2">
                        <div
                          className={`absolute top-1 h-5 rounded-md ${task.critical ? 'bg-rose-500/80' : 'bg-primary/70'}`}
                          style={{ left: `${bar.left}%`, width: `${bar.width}%` }}
                          title={`${task.title} · ${task.duration_days} days · float ${task.total_float_days}`}
                        />
                      </div>
                      <div />
                      <div className="flex flex-wrap gap-2 text-[10px] text-muted">
                        {task.critical && <span className="font-bold text-rose-600">Critical path</span>}
                        {shifted && <span>Original {dateLabel(task.start_date)} → {dateLabel(task.end_date)}</span>}
                        <span>Float {num(task.total_float_days)}d</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </SectionCard>

          <div className="grid gap-5 xl:grid-cols-3">
            <SectionCard title="Dependencies" description="FS · SS · FF · SF with lag in days">
              <DataTable
                columns={[
                  { key: 'type', label: 'Type', render: (row) => <span className="font-bold text-ink">{row.type}</span> },
                  { key: 'predecessor_id', label: 'Predecessor', render: (row) => dependencyTitles[row.predecessor_id] ?? row.predecessor_id },
                  { key: 'successor_id', label: 'Successor', render: (row) => dependencyTitles[row.successor_id] ?? row.successor_id },
                  { key: 'lag_days', label: 'Lag', align: 'right', render: (row) => `${num(row.lag_days)}d` },
                ]}
                rows={data.dependencies ?? []}
                rowKey={(row) => row.dependency_id}
                empty={<p className="p-5 text-xs text-muted">No active dependencies.</p>}
              />
            </SectionCard>
            <SectionCard title="Critical path">
              <div className="p-5">
                <p className="text-2xl font-bold text-ink">{num(critical?.total_days ?? 0)} days</p>
                <ol className="mt-3 space-y-2 text-xs text-ink-soft">
                  {(critical?.steps ?? []).map((step, index) => (
                    <li key={step.work_item_id}>{index + 1}. {step.title} <span className="text-muted">({dateLabel(step.start_date)} → {dateLabel(step.end_date)})</span></li>
                  ))}
                </ol>
              </div>
            </SectionCard>
            <SectionCard title="Schedule variance">
              <DataTable
                columns={[
                  { key: 'title', label: 'Item' },
                  { key: 'baseline_end', label: 'Baseline', render: (row) => <DateCell value={row.baseline_end} /> },
                  { key: 'current_end', label: 'Current', render: (row) => <DateCell value={row.current_end} /> },
                  { key: 'end_variance_days', label: 'Variance', align: 'right', render: (row) => `${num(row.end_variance_days)}d` },
                ]}
                rows={variance}
                rowKey={(row) => row.entity_id}
                empty={<p className="p-5 text-xs text-muted">No approved baseline yet.</p>}
              />
            </SectionCard>
          </div>
        </div>
      )}

      <Modal
        open={baselineOpen}
        onClose={() => setBaselineOpen(false)}
        title="Create approved baseline"
        description="Baseline changes require an approved change request or approval record."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setBaselineOpen(false)}>Cancel</button>
            <button type="button" className="btn-primary" onClick={saveBaseline}>Create baseline</button>
          </>
        }
      >
        <FormGrid
          fields={[
            { name: 'name', label: 'Baseline name', required: true },
            refField('change_request_id', 'Approved change request', 'changeRequests'),
            refField('approval_id', 'Approved record', 'approvals'),
            { name: 'comment', label: 'Comment', type: 'textarea' },
          ]}
          values={baselineValues}
          onChange={(name, value) => setBaselineValues((current) => ({ ...current, [name]: value }))}
        />
      </Modal>
    </>
  )
}

export function ImportsPage() {
  const can = useCan()
  const [searchParams] = useSearchParams()
  const [batches, setBatches] = useState([])
  const [batch, setBatch] = useState(null)
  const [batchId, setBatchId] = useState(searchParams.get('batch') ?? '')
  const [values, setValues] = useState({ provider: 'csv', mapping: '{\n  "title": "Title",\n  "project_id": "Project ID"\n}', rows: '[\n  {"Title": "Example", "Project ID": ""}\n]', file_document_id: '' })
  const [decision, setDecision] = useState({ mapping: '', comment: '', approved: true })
  const [busy, setBusy] = useState(false)

  const loadBatches = useCallback(async () => {
    try {
      const response = await api.get('/projects/import-batches', { params: { size: 30 } })
      setBatches(toRows(response.data))
    } catch {
      setBatches([])
    }
  }, [])

  const loadBatch = useCallback(async (id) => {
    if (!id) {
      setBatch(null)
      return
    }
    try {
      const response = await api.get(`/projects/imports/${id}`)
      setBatch(response.data)
      setDecision((current) => ({ ...current, mapping: JSON.stringify(response.data.mapping_json ?? {}, null, 2) }))
    } catch (error) {
      toast.error('Could not load import batch', apiErrorMessage(error))
    }
  }, [])

  useEffect(() => {
    loadBatches()
  }, [loadBatches])

  useEffect(() => {
    loadBatch(batchId)
  }, [batchId, loadBatch])

  const stage = async () => {
    const mapping = parseJson(values.mapping, 'mapping')
    const rows = parseJson(values.rows, 'rows')
    if (!mapping || !Array.isArray(rows)) return
    setBusy(true)
    try {
      const response = await api.post('/projects/imports', {
        provider: values.provider,
        mapping,
        rows,
        file_document_id: values.file_document_id || null,
      })
      toast.success('Import staged', 'Review the validation report before approving.')
      await loadBatches()
      setBatchId(response.data.id)
    } catch (error) {
      toast.error('Could not stage import', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const decide = async (approved) => {
    const mapping = parseJson(decision.mapping, 'mapping')
    if (!mapping) return
    setBusy(true)
    try {
      await api.post(`/projects/imports/${batchId}/approve`, { mapping, approved, comment: decision.comment || null })
      toast.success(approved ? 'Mapping approved' : 'Import rejected', approved ? 'A dry-run plan is now available.' : 'No records will be created.')
      await loadBatch(batchId)
      await loadBatches()
    } catch (error) {
      toast.error('Could not update import', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const runAction = async (action) => {
    setBusy(true)
    try {
      await api.post(`/projects/imports/${batchId}/${action}`)
      toast.success(`Import ${action === 'commit' ? 'committed' : 'rolled back'}`, 'The batch status was updated.')
      await loadBatch(batchId)
      await loadBatches()
    } catch (error) {
      toast.error(`Could not ${action} import`, apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const rows = batch?.payload_json?.rows ?? []
  const plan = batch?.dry_run_json?.plan ?? []
  const canManage = can('projects.settings.manage')

  return (
    <>
      <PageHeader
        eyebrow="Projects"
        title="Imports"
        description="Stage external rows, validate the mapping, approve the plan, then commit or roll back."
        actions={<button type="button" className="btn-secondary" onClick={() => { loadBatch(batchId); loadBatches() }}><RefreshCw size={15} /> Refresh</button>}
      />
      <div className="grid gap-5 xl:grid-cols-2">
        <SectionCard title="Stage an import" description="Rows are staged for review; nothing is written until commit." bodyClassName="space-y-4 p-5">
          <FormGrid
            fields={[
              { name: 'provider', label: 'Provider', type: 'select', options: ['csv', 'jira', 'microsoft_project'], required: true },
              { name: 'file_document_id', label: 'Source document ID', help: 'Store the file in Documents and paste its ID here.' },
              { name: 'mapping', label: 'Field mapping JSON', type: 'json', required: true, help: 'Target field → source column, e.g. title ← Title.' },
              { name: 'rows', label: 'Rows JSON', type: 'json', required: true, help: 'Array of source objects. Each row needs a title/name and project_id for work items.' },
            ]}
            values={values}
            onChange={(name, value) => setValues((current) => ({ ...current, [name]: value }))}
          />
          {canManage && <button type="button" className="btn-primary" onClick={stage} disabled={busy}><Upload size={15} /> Stage rows</button>}
        </SectionCard>

        <SectionCard title="Import batches" description="Select a batch to inspect its staging rows and validation report.">
          <DataTable
            columns={[
              { key: 'provider', label: 'Provider', render: (row) => titleCase(row.provider) },
              { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
              { key: 'rows_total', label: 'Rows', align: 'right', render: (row) => num(row.rows_total) },
              { key: 'rows_failed', label: 'Failed', align: 'right', render: (row) => num(row.rows_failed) },
              { key: 'created_at', label: 'Created', render: (row) => <DateCell value={row.created_at} /> },
            ]}
            rows={batches}
            rowKey={(row) => row.id}
            empty={<p className="p-5 text-xs text-muted">No import batches yet.</p>}
            onRowClick={(row) => setBatchId(row.id)}
          />
        </SectionCard>
      </div>

      {batch && (
        <div className="mt-5 space-y-5">
          <div className="card flex flex-wrap items-center justify-between gap-3 px-5 py-4">
            <div>
              <p className="text-xs font-bold text-ink">{titleCase(batch.provider)} import</p>
              <p className="text-[11px] text-muted">{num(batch.rows_total)} rows · {num(batch.rows_failed)} failed · {dateLabel(batch.created_at)}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Status value={batch.status} />
              {canManage && batch.status === 'approved' && <button type="button" className="btn-primary" onClick={() => runAction('commit')} disabled={busy}>Commit import</button>}
              {canManage && batch.status === 'committed' && <button type="button" className="btn-secondary" onClick={() => runAction('rollback')} disabled={busy}>Roll back</button>}
            </div>
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            <SectionCard title="Mapping approval" description="Review the normalized field map before a dry run." bodyClassName="space-y-3 p-5">
              <FormGrid
                fields={[
                  { name: 'mapping', label: 'Mapping JSON', type: 'json' },
                  { name: 'comment', label: 'Decision comment', type: 'textarea' },
                ]}
                values={decision}
                onChange={(name, value) => setDecision((current) => ({ ...current, [name]: value }))}
              />
              {canManage && ['staged', 'validated'].includes(batch.status) && (
                <div className="flex gap-2">
                  <button type="button" className="btn-primary" onClick={() => decide(true)} disabled={busy}>Approve mapping</button>
                  <button type="button" className="btn-secondary" onClick={() => decide(false)} disabled={busy}>Reject</button>
                </div>
              )}
            </SectionCard>

            <SectionCard title="Validation report" description={plan.length ? `${plan.length} staged rows checked` : 'Approve the mapping to generate a dry-run plan.'}>
              <DataTable
                columns={[
                  { key: 'row_id', label: 'Staging row', render: (row) => String(row.row_id).slice(0, 8) },
                  { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
                  { key: 'errors', label: 'Errors', render: (row) => row.errors?.length ? row.errors.join(', ') : '—' },
                ]}
                rows={plan}
                rowKey={(row) => row.row_id}
                empty={<p className="p-5 text-xs text-muted">No validation report yet.</p>}
              />
            </SectionCard>
          </div>

          <SectionCard title="Staged rows" description="Source rows are stored in payload_json; no separate row endpoint is used.">
            <DataTable
              columns={[
                { key: 'title', label: 'Title', render: (row) => row.title || row.name || row.Title || '—' },
                { key: 'project_id', label: 'Project ID', render: (row) => row.project_id || row['Project ID'] || '—' },
                { key: 'status', label: 'Status', render: (row) => row.status || row.Status || '—' },
                { key: 'external_id', label: 'External ID', render: (row) => row.external_id || '—' },
              ]}
              rows={rows}
              rowKey={(row) => String(row.external_id ?? row.key ?? JSON.stringify(row))}
              empty={<p className="p-5 text-xs text-muted">No staged rows in this batch.</p>}
            />
          </SectionCard>
        </div>
      )}
    </>
  )
}

export function IntakePage() {
  const can = useCan()
  const [values, setValues] = useState({ title: '', objective: '', sponsor: '', budget_range: '', requested_start_date: '', requested_end_date: '', template_id: '', customer_id: '', currency: 'INR' })
  const [approvals, setApprovals] = useState([])
  const [decision, setDecision] = useState({ approval_id: '', decision: 'approve', comment: '', clarification: '' })
  const [created, setCreated] = useState(null)

  const loadApprovals = useCallback(async () => {
    try {
      const response = await api.get('/projects/approvals', { params: { approval_type: 'intake', status: 'pending', size: 50 } })
      setApprovals(toRows(response.data))
    } catch {
      setApprovals([])
    }
  }, [])

  useEffect(() => {
    loadApprovals()
  }, [loadApprovals])

  const submit = async () => {
    try {
      const response = await api.post('/projects/intake', {
        title: values.title,
        objective: values.objective,
        sponsor: values.sponsor || null,
        budget_range: values.budget_range || null,
        requested_start_date: values.requested_start_date || null,
        requested_end_date: values.requested_end_date || null,
        template_id: values.template_id || null,
        customer_id: values.customer_id || null,
        currency: values.currency || 'INR',
      })
      toast.success('Intake submitted', 'An intake approval record was created.')
      setCreated(response.data)
      await loadApprovals()
      if (response.data.entity_id) setDecision((current) => ({ ...current, approval_id: response.data.id }))
    } catch (error) {
      toast.error('Could not submit intake', apiErrorMessage(error))
    }
  }

  const decide = async () => {
    if (!decision.approval_id) {
      toast.error('Select an approval', 'Choose a pending intake request first.')
      return
    }
    try {
      const project = await api.post(`/projects/intake/${decision.approval_id}/decide`, {
        decision: decision.decision,
        comment: decision.comment || null,
        clarification: decision.clarification || null,
      })
      toast.success('Intake decision recorded', decision.decision === 'approve' ? 'A draft project was created.' : 'The intake was rejected.')
      setCreated(project.data)
      await loadApprovals()
    } catch (error) {
      toast.error('Could not decide intake', apiErrorMessage(error))
    }
  }

  return (
    <>
      <PageHeader eyebrow="Projects" title="Project intake" description="Submit a request and approve it into a draft project with template structure." />
      {created?.entity_id && (
        <div className="card mb-5 px-5 py-4 text-sm">
          Latest result: <Link className="font-bold text-accent hover:underline" to={`/projects/projects/${created.entity_id}`}>Open project workspace</Link>
        </div>
      )}
      <div className="grid gap-5 xl:grid-cols-2">
        <SectionCard title="Submit a request" bodyClassName="space-y-4 p-5">
          <FormGrid
            fields={[
              { name: 'title', label: 'Title', required: true },
              { name: 'objective', label: 'Objective', type: 'textarea', required: true },
              { name: 'sponsor', label: 'Sponsor' },
              { name: 'budget_range', label: 'Budget range', type: 'number' },
              { name: 'requested_start_date', label: 'Requested start', type: 'date' },
              { name: 'requested_end_date', label: 'Requested end', type: 'date' },
              refField('template_id', 'Template', 'templates'),
              refField('customer_id', 'Customer', 'customers'),
              { name: 'currency', label: 'Currency', default: 'INR' },
            ]}
            values={values}
            onChange={(name, value) => setValues((current) => ({ ...current, [name]: value }))}
          />
          {can('projects.project.create') && <button type="button" className="btn-primary" onClick={submit}>Submit intake</button>}
        </SectionCard>

        <SectionCard title="Decision queue" description="Pending intake approvals">
          <div className="space-y-4 p-5">
            <select className="input" value={decision.approval_id} onChange={(event) => setDecision((current) => ({ ...current, approval_id: event.target.value }))}>
              <option value="">Select pending intake…</option>
              {approvals.map((approval) => <option key={approval.id} value={approval.id}>{approval.comments || approval.entity_id}</option>)}
            </select>
            <FormGrid
              fields={[
                { name: 'decision', label: 'Decision', type: 'select', options: ['approve', 'reject'], required: true },
                { name: 'comment', label: 'Comment', type: 'textarea' },
                { name: 'clarification', label: 'Clarification requested', type: 'textarea' },
              ]}
              values={decision}
              onChange={(name, value) => setDecision((current) => ({ ...current, [name]: value }))}
            />
            {can('projects.approval.update') && <button type="button" className="btn-primary" onClick={decide}>Record decision</button>}
          </div>
        </SectionCard>
      </div>
    </>
  )
}

export function NotificationsPage() {
  const can = useCan()
  const [searchParams] = useSearchParams()
  const projects = useProjectOptions()
  const [values, setValues] = useState({
    channel: 'email',
    to: '',
    template: 'project.update',
    body: '',
    entity_type: 'project',
    entity_id: searchParams.get('project_id') ?? '',
    consent_reference: '',
  })
  const [activity, setActivity] = useState([])

  useEffect(() => {
    if (!values.entity_id && projects.length) setValues((current) => ({ ...current, entity_id: projects[0].value }))
  }, [projects, values.entity_id])

  const loadActivity = useCallback(async () => {
    try {
      const response = await api.get('/projects/activities', { params: { action: 'notification.sent', size: 30 } })
      setActivity(toRows(response.data))
    } catch {
      setActivity([])
    }
  }, [])

  useEffect(() => {
    loadActivity()
  }, [loadActivity])

  const send = async () => {
    try {
      await api.post('/projects/notifications', values)
      toast.success('Notification queued', 'The message provider accepted the request.')
      await loadActivity()
    } catch (error) {
      toast.error('Could not send notification', apiErrorMessage(error))
    }
  }

  const entityLookups = { project: 'projects', work_item: 'workItems', milestone: 'milestones', risk: 'risks' }

  return (
    <>
      <PageHeader eyebrow="Projects" title="Notifications" description="Send templated messages through the messaging service; WhatsApp requires a consent reference." />
      <div className="grid gap-5 xl:grid-cols-2">
        <SectionCard title="Send a notification" bodyClassName="space-y-4 p-5">
          <FormGrid
            fields={[
              { name: 'channel', label: 'Channel', type: 'select', options: ['email', 'whatsapp', 'calendar'], required: true },
              { name: 'to', label: 'Recipient', required: true },
              { name: 'template', label: 'Template code', required: true },
              { name: 'body', label: 'Message', type: 'textarea', required: true },
              { name: 'entity_type', label: 'Entity type', type: 'select', options: ['project', 'work_item', 'milestone', 'risk'], required: true },
              { name: 'consent_reference', label: 'Consent reference' },
            ]}
            values={values}
            onChange={(name, value) => setValues((current) => ({ ...current, [name]: value }))}
          />
          <RemoteSelect
            lookup={entityLookups[values.entity_type] ?? 'projects'}
            value={values.entity_id}
            onChange={(value) => setValues((current) => ({ ...current, entity_id: value }))}
            placeholder="Select entity"
          />
          {can('projects.comment.create') && <button type="button" className="btn-primary" onClick={send}>Send notification</button>}
        </SectionCard>

        <SectionCard title="Recent delivery messages">
          <DataTable
            columns={[
              { key: 'template', label: 'Template', render: (row) => row.template_code ?? row.template ?? '—' },
              { key: 'channel', label: 'Channel', render: (row) => titleCase(asObject(row.changes_json).channel ?? '—') },
              { key: 'recipient', label: 'Recipient', render: (row) => row.recipient ?? '—' },
              { key: 'created_at', label: 'Sent', render: (row) => <DateCell value={row.created_at} /> },
            ]}
            rows={activity}
            rowKey={(row) => row.id}
            empty={<p className="p-5 text-xs text-muted">No messages sent yet.</p>}
          />
        </SectionCard>
      </div>
    </>
  )
}
