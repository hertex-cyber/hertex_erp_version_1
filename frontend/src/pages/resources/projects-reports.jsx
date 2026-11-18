import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Clock3,
  FolderKanban,
  Inbox,
  ListChecks,
  ShieldAlert,
  Sparkles,
  Wallet,
  XCircle,
} from 'lucide-react'
import { DataTable } from '../../components/DataTable'
import { RemoteSelect } from '../../components/Form'
import { DateCell, Money, Primary, Ref, Status, TypeBadge } from '../../components/cells'
import { EmptyState, KpiCard, PageHeader, SectionCard } from '../../components/ui'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel, money, num, pct, titleCase } from '../../lib/format'
import { fetchLookup } from '../../lib/lookups'
import { earnedValue, filterReportRows, topFeatures } from '../../lib/project-helpers'
import { useAuth } from '../../store/auth'

export const REPORT_DEFINITIONS = [
  {
    key: 'health',
    label: 'Project health',
    description: 'Composite delivery health, blockers, risk score and schedule variance.',
    endpoint: '/projects/reports/health',
    icon: Activity,
    columns: [
      { key: 'name', label: 'Project', render: (row) => <Primary title={row.name} subtitle={titleCase(row.status)} /> },
      { key: 'health', label: 'Health', render: (row) => <Status value={row.health} /> },
      { key: 'blockers', label: 'Blockers', align: 'right', render: (row) => num(row.blockers) },
      { key: 'risk_score', label: 'Risk score', align: 'right', render: (row) => num(row.risk_score, 2) },
      { key: 'schedule_variance_days', label: 'Schedule variance', align: 'right', render: (row) => `${num(row.schedule_variance_days)}d` },
      { key: 'budget', label: 'Budget', align: 'right', finance: true, render: (row) => <Money value={row.budget} currency={row.currency} restricted /> },
      { key: 'wip', label: 'WIP', align: 'right', finance: true, render: (row) => <Money value={row.wip} currency={row.currency} restricted /> },
      { key: 'margin', label: 'Margin', align: 'right', finance: true, render: (row) => <Money value={row.margin} currency={row.currency} restricted /> },
    ],
    chart: { name: (row) => row.name, series: [{ key: 'blockers', label: 'Blockers' }, { key: 'risk_score', label: 'Risk score' }] },
  },
  {
    key: 'budget_vs_actual',
    label: 'Budget vs actual',
    description: 'Budget cost, billed value, committed cost and margin by project.',
    endpoint: '/projects/reports/budget_vs_actual',
    icon: Wallet,
    finance: true,
    columns: [
      projectColumn(),
      moneyReportColumn('budget', 'Budget'),
      moneyReportColumn('billed', 'Billed'),
      moneyReportColumn('cost', 'Cost'),
      moneyReportColumn('wip', 'WIP'),
      moneyReportColumn('margin', 'Margin'),
    ],
    chart: { name: (row) => row.name, series: [{ key: 'budget', label: 'Budget' }, { key: 'billed', label: 'Billed' }, { key: 'cost', label: 'Cost' }] },
  },
  {
    key: 'earned_value',
    label: 'Earned value',
    description: 'EAC, ETC, CPI and SPI derived from baseline, earned and actual values.',
    endpoint: '/projects/reports/earned_value',
    icon: BarChart3,
    finance: true,
    columns: [
      projectColumn(),
      { key: 'planned_hours', label: 'Planned hours', align: 'right', render: (row) => num(row.planned_hours, 1) },
      { key: 'actual_hours', label: 'Actual hours', align: 'right', render: (row) => num(row.actual_hours, 1) },
      { key: 'earned_value', label: 'Earned value', align: 'right', finance: true, render: (row) => <Money value={row.earned_value} currency={row.currency} restricted /> },
      { key: 'cpi', label: 'CPI', align: 'right', render: (row) => num(row.cpi, 2) },
      { key: 'spi', label: 'SPI', align: 'right', render: (row) => num(row.spi, 2) },
      { key: 'eac', label: 'EAC', align: 'right', finance: true, render: (row) => <Money value={earnedValue(row).eac} currency={row.currency} restricted /> },
      { key: 'etc', label: 'ETC', align: 'right', finance: true, render: (row) => <Money value={earnedValue(row).etc} currency={row.currency} restricted /> },
    ],
    chart: { name: (row) => row.name, series: [{ key: 'cpi', label: 'CPI' }, { key: 'spi', label: 'SPI' }] },
  },
  {
    key: 'utilisation',
    label: 'Utilisation',
    description: 'Booked and actual hours against leave-adjusted capacity by employee and week.',
    endpoint: '/projects/reports/utilisation',
    icon: Clock3,
    columns: [
      { key: 'employee_name', label: 'Employee', render: (row) => <Primary title={row.employee_name ?? row.employee_id} subtitle={dateLabel(row.week_start)} /> },
      dateReportColumn('week_start', 'Week'),
      { key: 'capacity_hours', label: 'Capacity', align: 'right', render: (row) => num(row.capacity_hours, 1) },
      { key: 'booked_hours', label: 'Booked', align: 'right', render: (row) => num(row.booked_hours, 1) },
      { key: 'planned_leave_hours', label: 'Leave', align: 'right', render: (row) => num(row.planned_leave_hours, 1) },
      { key: 'available_hours', label: 'Available', align: 'right', render: (row) => num(row.available_hours, 1) },
      { key: 'utilization_percent', label: 'Utilisation', align: 'right', render: (row) => pct(row.utilization_percent, 1) },
      { key: 'overallocated', label: 'Status', render: (row) => <Status value={row.overallocated ? 'escalated' : 'active'} /> },
    ],
    chart: { name: (row) => row.employee_name ?? row.employee_id, series: [{ key: 'utilization_percent', label: 'Utilisation %' }] },
  },
  {
    key: 'workload',
    label: 'Workload heatmap',
    description: 'Weekly bookings against HR-adjusted capacity, including overallocation flags.',
    endpoint: '/projects/reports/workload',
    icon: BarChart3,
    columns: [
      { key: 'employee_name', label: 'Employee', render: (row) => <Primary title={row.employee_name ?? row.employee_id} subtitle={dateLabel(row.week_start)} /> },
      dateReportColumn('week_start', 'Week'),
      { key: 'booked_hours', label: 'Booked', align: 'right', render: (row) => num(row.booked_hours, 1) },
      { key: 'available_hours', label: 'Available', align: 'right', render: (row) => num(row.available_hours, 1) },
      { key: 'utilization_percent', label: 'Load', align: 'right', render: (row) => pct(row.utilization_percent, 1) },
      { key: 'overallocated', label: 'Flag', render: (row) => <Status value={row.overallocated ? 'escalated' : 'active'} /> },
    ],
    chart: { name: (row) => `${String(row.employee_name ?? row.employee_id ?? '').slice(0, 12)} ${dateLabel(row.week_start)}`, series: [{ key: 'booked_hours', label: 'Booked' }, { key: 'available_hours', label: 'Available' }] },
  },
  {
    key: 'unbilled_wip',
    label: 'Unbilled WIP',
    description: 'Approved billable time, expenses and accepted milestones not yet invoiced.',
    endpoint: '/projects/reports/unbilled_wip',
    icon: Wallet,
    finance: true,
    columns: [
      projectColumn(),
      { key: 'billing_type', label: 'Billing type', render: (row) => <TypeBadge value={row.billing_type} /> },
      { key: 'lines', label: 'Lines', align: 'right', render: (row) => num(row.lines) },
      moneyReportColumn('total', 'Unbilled total'),
    ],
    chart: { name: (row) => row.name ?? row.project_id, series: [{ key: 'total', label: 'Unbilled' }] },
  },
  {
    key: 'billing_leakage',
    label: 'Billing leakage',
    description: 'Billable work items missing approved time or billing lines.',
    endpoint: '/projects/reports/billing_leakage',
    icon: Wallet,
    columns: [
      projectColumn(),
      { key: 'billing_type', label: 'Billing type', render: (row) => <TypeBadge value={row.billing_type} /> },
      { key: 'billable_work_items', label: 'Billable items', align: 'right', render: (row) => num(row.billable_work_items) },
      { key: 'without_approved_time', label: 'Missing approved time', align: 'right', render: (row) => num(row.without_approved_time) },
      moneyReportColumn('total', 'Exposure'),
    ],
    chart: { name: (row) => row.name ?? row.project_id, series: [{ key: 'without_approved_time', label: 'Missing time' }] },
  },
  {
    key: 'velocity',
    label: 'Velocity',
    description: 'Completed story points, throughput and carryover by sprint and team.',
    endpoint: '/projects/reports/velocity',
    icon: BarChart3,
    columns: [
      { key: 'name', label: 'Sprint', render: (row) => <Primary title={row.name} subtitle={dateLabel(row.end_date)} /> },
      projectColumn(),
      { key: 'velocity', label: 'Velocity', align: 'right', render: (row) => num(row.velocity, 1) },
      { key: 'throughput', label: 'Throughput', align: 'right', render: (row) => num(row.throughput) },
      { key: 'carryover', label: 'Carryover', align: 'right', render: (row) => num(row.carryover) },
    ],
    chart: { name: (row) => row.name, series: [{ key: 'velocity', label: 'Velocity' }, { key: 'carryover', label: 'Carryover' }] },
  },
  {
    key: 'cycle_lead_time',
    label: 'Cycle & lead time',
    description: 'Work item first-start to done and created to done distributions.',
    endpoint: '/projects/reports/cycle_lead_time',
    icon: Clock3,
    columns: [
      { key: 'work_item_id', label: 'Work item', render: (row) => <Ref lookup="workItems" id={row.work_item_id} /> },
      projectColumn(),
      { key: 'cycle_time_days', label: 'Cycle time', align: 'right', render: (row) => `${num(row.cycle_time_days, 1)}d` },
      { key: 'lead_time_days', label: 'Lead time', align: 'right', render: (row) => `${num(row.lead_time_days, 1)}d` },
    ],
    chart: { name: (row) => String(row.work_item_id ?? '').slice(0, 8), series: [{ key: 'cycle_time_days', label: 'Cycle days' }, { key: 'lead_time_days', label: 'Lead days' }] },
  },
  {
    key: 'cumulative_flow',
    label: 'Cumulative flow',
    description: 'Work item counts by status category over the reporting window.',
    endpoint: '/projects/reports/cumulative_flow',
    icon: BarChart3,
    columns: [
      projectColumn(),
      { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
      { key: 'count', label: 'Items', align: 'right', render: (row) => num(row.count) },
    ],
    chart: { name: (row) => titleCase(row.status), series: [{ key: 'count', label: 'Items' }] },
  },
  {
    key: 'throughput_rework',
    label: 'Throughput & rework',
    description: 'Completed items and reopened items by period.',
    endpoint: '/projects/reports/throughput_rework',
    icon: Activity,
    columns: [
      { key: 'work_item_id', label: 'Work item', render: (row) => <Ref lookup="workItems" id={row.work_item_id} /> },
      projectColumn(),
      { key: 'completed', label: 'Completed', render: (row) => <Status value={row.completed ? 'done' : 'open'} /> },
      { key: 'reopened_count', label: 'Reopened', align: 'right', render: (row) => num(row.reopened_count) },
    ],
    chart: { name: (row) => String(row.work_item_id ?? '').slice(0, 8), series: [{ key: 'reopened_count', label: 'Reopened' }] },
  },
  {
    key: 'risk_heatmap',
    label: 'Risk heatmap',
    description: 'Probability × impact scores with escalation status by project and portfolio.',
    endpoint: '/projects/reports/risk_heatmap',
    icon: ShieldAlert,
    columns: [
      { key: 'title', label: 'Risk', render: (row) => <Primary title={row.title} subtitle={titleCase(row.status)} /> },
      projectColumn(),
      { key: 'probability', label: 'Probability', align: 'right', render: (row) => num(row.probability, 1) },
      { key: 'impact', label: 'Impact', align: 'right', render: (row) => num(row.impact, 1) },
      { key: 'score', label: 'Score', align: 'right', render: (row) => num(row.score, 1) },
      { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
    ],
    chart: { name: (row) => String(row.title ?? '').slice(0, 16), series: [{ key: 'score', label: 'Score' }] },
  },
  {
    key: 'milestone_schedule',
    label: 'Milestone schedule',
    description: 'Planned versus accepted milestones and billing state.',
    endpoint: '/projects/reports/milestone_schedule',
    icon: CheckCircle2,
    columns: [
      { key: 'name', label: 'Milestone', render: (row) => <Primary title={row.name} subtitle={titleCase(row.status)} /> },
      projectColumn(),
      dateReportColumn('due_date', 'Due'),
      dateReportColumn('accepted_at', 'Accepted'),
      moneyReportColumn('amount', 'Amount'),
      { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
    ],
    chart: { name: (row) => String(row.name ?? '').slice(0, 16), series: [{ key: 'amount', label: 'Amount' }] },
  },
  {
    key: 'timesheet_compliance',
    label: 'Timesheet compliance',
    description: 'Submitted, approved, rejected and late timesheets by team.',
    endpoint: '/projects/reports/timesheet_compliance',
    icon: Clock3,
    columns: [
      { key: 'timesheet_id', label: 'Timesheet', render: (row) => <Ref lookup="timesheets" id={row.timesheet_id} /> },
      { key: 'employee_id', label: 'Employee', render: (row) => <Ref lookup="employees" id={row.employee_id} /> },
      dateReportColumn('week_start', 'Week'),
      { key: 'hours', label: 'Hours', align: 'right', render: (row) => num(row.hours, 1) },
      { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
      dateReportColumn('submitted_at', 'Submitted'),
    ],
    chart: { name: (row) => String(row.week_start ?? '').slice(0, 10), series: [{ key: 'hours', label: 'Hours' }] },
  },
  {
    key: 'portfolio_benefits',
    label: 'Portfolio benefits',
    description: 'Goal and OKR target versus current value by portfolio, program and project.',
    endpoint: '/projects/reports/portfolio_benefits',
    icon: FolderKanban,
    columns: [
      { key: 'title', label: 'Goal', render: (row) => <Primary title={row.title} subtitle={row.metric} /> },
      { key: 'portfolio_id', label: 'Portfolio', render: (row) => <Ref lookup="portfolios" id={row.portfolio_id} /> },
      { key: 'program_id', label: 'Program', render: (row) => <Ref lookup="programs" id={row.program_id} /> },
      { key: 'target', label: 'Target', align: 'right', render: (row) => num(row.target, 1) },
      { key: 'current', label: 'Current', align: 'right', render: (row) => num(row.current, 1) },
      { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
    ],
    chart: { name: (row) => String(row.title ?? '').slice(0, 16), series: [{ key: 'target', label: 'Target' }, { key: 'current', label: 'Current' }] },
  },
  {
    key: 'ai_governance',
    label: 'AI governance',
    description: 'Signals and actions by type, score, review state and reversal reference.',
    endpoint: '/projects/reports/ai_governance',
    icon: Sparkles,
    columns: [
      { key: 'type', label: 'Type', render: (row) => <TypeBadge value={row.type} /> },
      { key: 'signal_type', label: 'Signal / action', render: (row) => <Primary title={titleCase(row.signal_type ?? row.action_type)} subtitle={String(row.id ?? '').slice(0, 8)} /> },
      { key: 'score', label: 'Score', align: 'right', render: (row) => num(row.score, 2) },
      { key: 'review_status', label: 'Review', render: (row) => <Status value={row.review_status ?? row.status} /> },
      { key: 'model_version', label: 'Model' },
      dateReportColumn('generated_at', 'Generated'),
      {
        key: 'features',
        label: 'Top 3 features',
        render: (row) => (
          <div className="flex flex-wrap gap-1">
            {topFeatures(row.features).map(([name, value]) => (
              <span key={name} className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-soft">
                {titleCase(name)}: {num(value, 2)}
              </span>
            ))}
          </div>
        ),
      },
      { key: 'reversal_reference', label: 'Reversal' },
    ],
    chart: { name: (row) => titleCase(row.signal_type ?? row.action_type ?? row.type), series: [{ key: 'score', label: 'Score' }] },
  },
]

function projectColumn() {
  return { key: 'project_id', label: 'Project', render: (row) => <Ref lookup="projects" id={row.project_id} /> }
}

function dateReportColumn(key, label) {
  return { key, label, render: (row) => <DateCell value={row[key]} /> }
}

function moneyReportColumn(key, label) {
  return {
    key,
    label,
    align: 'right',
    finance: true,
    render: (row) => <Money value={row[key]} currency={row.currency ?? row.project_currency} restricted />,
  }
}

function ReportChart({ report, rows }) {
  if (!report.chart || !rows.length) return null
  const data = rows.slice(0, 12).map((row) => {
    const point = { name: report.chart.name(row) ?? '—' }
    for (const series of report.chart.series) point[series.label] = Number(row[series.key] ?? 0) || 0
    return point
  })
  return (
    <div className="h-52 px-4 pb-4">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#78716c' }} interval={0} />
          <YAxis tick={{ fontSize: 10, fill: '#78716c' }} width={44} />
          <Tooltip formatter={(value) => num(value, 2)} />
          {report.chart.series.map((series, index) => (
            <Bar key={series.key} dataKey={series.label} fill={index === 0 ? '#ff6900' : '#a1a1aa'} radius={[4, 4, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function ReportTable({ report, filters, restricted }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const extractRef = useRef(null)
  const filtersRef = useRef(filters)
  filtersRef.current = filters
  extractRef.current = (data) => data?.rows ?? data?.items ?? (Array.isArray(data) ? data : [])
  const params = useMemo(
    () => ({
      project_id: filters.projectId || undefined,
      date_from: filters.dateFrom || undefined,
      date_to: filters.dateTo || undefined,
      team: filters.team || undefined,
    }),
    [filters.projectId, filters.dateFrom, filters.dateTo, filters.team],
  )
  const paramsKey = JSON.stringify(params)

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    api
      .get(report.endpoint, { params })
      .then(({ data }) => {
        if (active) setRows(filterReportRows(extractRef.current(data), filtersRef.current))
      })
      .catch((requestError) => {
        if (active) {
          setRows([])
          setError(apiErrorMessage(requestError, 'This report could not be loaded.'))
        }
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [report.endpoint, paramsKey])

  const columns = report.columns.filter((column) => !column.finance || !restricted)

  return (
    <SectionCard
      title={report.label}
      description={report.description}
      action={
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted">
          {num(rows.length)} rows
        </span>
      }
      bodyClassName="p-0"
    >
      {restricted && report.finance && (
        <p className="border-b border-line bg-surface-2 px-5 py-2 text-[11px] font-semibold text-muted">
          Restricted: financial fields require projects.finance.read.
        </p>
      )}
      {error && <p className="border-b border-line px-5 py-2 text-[11px] text-rose-600">{error}</p>}
      <ReportChart report={report} rows={rows} />
      <DataTable
        columns={columns}
        rows={rows.map((row, index) => ({ ...row, __reportKey: row.id ?? row.project_id ?? index }))}
        rowKey={(row) => row.__reportKey}
        loading={loading}
        empty={<EmptyState compact title="No rows" description="No data is available for this report and filter selection." />}
      />
    </SectionCard>
  )
}

function ReportMetrics({ title, description, endpoint, params, metrics }) {
  const [data, setData] = useState(null)
  const paramsKey = JSON.stringify(params ?? {})

  useEffect(() => {
    let active = true
    api
      .get(endpoint, { params: params ?? {} })
      .then(({ data: response }) => {
        if (active) setData(response)
      })
      .catch(() => {
        if (active) setData(null)
      })
    return () => {
      active = false
    }
  }, [endpoint, paramsKey])

  return (
    <SectionCard title={title} description={description}>
      <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-4">
        {metrics.map((metric) => (
          <KpiCard
            key={metric.label}
            label={metric.label}
            value={metric.render ? metric.render(data?.[metric.key], data ?? {}) : num(data?.[metric.key])}
            icon={metric.icon}
          />
        ))}
      </div>
    </SectionCard>
  )
}

function OperationalReports({ filters, can }) {
  const projectId = filters.projectId
  const projectParams = projectId ? { project_id: projectId } : {}
  const overviewMetrics = [
    { label: 'Projects', key: 'total', icon: FolderKanban, render: (value, row) => (projectId ? num(row.total_tasks) : num(row.total)) },
    { label: 'Open work', key: 'open_tasks', icon: ListChecks },
    { label: 'Actual hours', key: 'actual_hours', icon: Clock3, render: (value) => num(value, 1) },
    ...(can('projects.finance.read')
      ? [{ label: 'Billable value', key: 'billable_value', icon: Wallet, render: (value) => money(value, { currency: filters.currency, restricted: true }) }]
      : []),
  ]
  return (
    <>
      <ReportMetrics
        title="Portfolio overview"
        description={projectId ? 'Summary for the selected project.' : 'Portfolio headline metrics.'}
        endpoint={projectId ? `/projects/projects/${projectId}/summary` : '/projects'}
        params={projectId ? undefined : { size: 1 }}
        metrics={overviewMetrics}
      />
      {projectId && (
        <ReportMetrics
          title="Governance"
          description="Open risks, issues and approvals for this project."
          endpoint="/projects/reports/governance"
          params={projectParams}
          metrics={[
            { label: 'Open risks', key: 'open_risks', icon: ShieldAlert },
            { label: 'Escalated', key: 'escalated_risks', icon: Activity },
            { label: 'Open issues', key: 'open_issues', icon: Activity },
            { label: 'Pending approvals', key: 'pending_approvals', icon: CheckCircle2 },
          ]}
        />
      )}
      {can('projects.finance.read') && (
        <ReportTable
          report={{
            key: 'profitability',
            label: 'Profitability',
            description: 'Budget versus billed revenue, cost and margin.',
            endpoint: '/projects/reports/profitability',
            columns: [
              projectColumn(),
              moneyReportColumn('budget_revenue', 'Budget revenue'),
              moneyReportColumn('billed', 'Billed'),
              moneyReportColumn('wip', 'WIP'),
              moneyReportColumn('labour_cost', 'Labour cost'),
              moneyReportColumn('expense_cost', 'Expenses'),
              moneyReportColumn('margin_amount', 'Margin'),
              { key: 'margin_percent', label: 'Margin %', align: 'right', render: (row) => pct(row.margin_percent, 2) },
            ],
          }}
          filters={filters}
          restricted={false}
        />
      )}
      <ReportTable
        report={{
          key: 'capacity',
          label: 'Capacity',
          description: 'Leave-aware availability by employee and week.',
          endpoint: '/projects/resources/capacity',
          columns: [
            { key: 'employee_name', label: 'Employee', render: (row) => <Primary title={row.employee_name ?? row.employee_id} subtitle={dateLabel(row.week_start)} /> },
            dateReportColumn('week_start', 'Week'),
            { key: 'capacity_hours', label: 'Capacity', align: 'right', render: (row) => num(row.capacity_hours, 1) },
            { key: 'planned_leave_hours', label: 'Leave', align: 'right', render: (row) => num(row.planned_leave_hours, 1) },
            { key: 'booked_hours', label: 'Booked', align: 'right', render: (row) => num(row.booked_hours, 1) },
            { key: 'available_hours', label: 'Available', align: 'right', render: (row) => num(row.available_hours, 1) },
            { key: 'utilization_percent', label: 'Utilisation', align: 'right', render: (row) => pct(row.utilization_percent, 1) },
            { key: 'overallocated', label: 'Status', render: (row) => <Status value={row.overallocated ? 'escalated' : 'active'} /> },
          ],
        }}
        filters={filters}
        restricted={false}
      />
      {projectId && can('projects.schedule.read') && (
        <ReportTable
          report={{
            key: 'critical_path',
            label: 'Critical path',
            description: 'Longest dependency chain for the selected project.',
            endpoint: `/projects/projects/${projectId}/critical-path`,
            columns: [
              { key: 'title', label: 'Work item', render: (row) => <Primary title={row.title} /> },
              dateReportColumn('start_date', 'Start'),
              dateReportColumn('end_date', 'End'),
              { key: 'duration_days', label: 'Days', align: 'right', render: (row) => num(row.duration_days) },
            ],
          }}
          filters={filters}
          restricted={false}
        />
      )}
      {can('projects.outbox.read') && (
        <ReportMetrics
          title="Event outbox"
          description="Delivery state of cross-module project events."
          endpoint="/projects/outbox/stats"
          metrics={[
            { label: 'Pending', key: 'pending', icon: Inbox },
            { label: 'Published', key: 'published', icon: CheckCircle2 },
            { label: 'Failed', key: 'failed', icon: XCircle },
          ]}
        />
      )}
    </>
  )
}

export default function ReportsPage() {
  const can = useAuth((state) => state.can)
  const [searchParams, setSearchParams] = useSearchParams()
  const [projects, setProjects] = useState([])
  const [projectId, setProjectId] = useState(searchParams.get('project_id') ?? '')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [team, setTeam] = useState('')
  const [showOperational, setShowOperational] = useState(false)
  const projectParam = searchParams.get('project_id') ?? ''
  const activeReport = searchParams.get('report') ?? ''
  const restricted = !can('projects.finance.read')

  useEffect(() => {
    fetchLookup('projects')
      .then(setProjects)
      .catch(() => setProjects([]))
  }, [])

  useEffect(() => {
    setProjectId(projectParam)
  }, [projectParam])

  const setReport = (key) => {
    const next = new URLSearchParams(searchParams)
    if (key) next.set('report', key)
    else next.delete('report')
    setSearchParams(next, { replace: true })
  }

  const setProject = (value) => {
    setProjectId(value ?? '')
    const next = new URLSearchParams(searchParams)
    if (value) next.set('project_id', value)
    else next.delete('project_id')
    setSearchParams(next, { replace: true })
  }

  const filters = { projectId, dateFrom, dateTo, team, currency: projects.find((item) => item.value === projectId)?.raw?.currency }
  const visibleReports = activeReport ? REPORT_DEFINITIONS.filter((report) => report.key === activeReport) : REPORT_DEFINITIONS

  if (!can('projects.report.read')) {
    return <EmptyState title="You don’t have access to this area" description="Ask an administrator for project report access." />
  }

  return (
    <>
      <PageHeader
        eyebrow="Projects"
        title="Project reports"
        description="All 16 plan reports: delivery health, money, flow, capacity, governance and AI review."
        actions={
          <Link to="/projects/ai-signals" className="btn-secondary">
            <Sparkles size={15} /> AI review queue
          </Link>
        }
      />
      <SectionCard title="Report filters" description="Project and date filters apply to every report below; team filters matching employee rows.">
        <div className="grid gap-3 p-5 md:grid-cols-4">
          <RemoteSelect lookup="projects" value={projectId} onChange={setProject} placeholder="All projects" />
          <label className="block">
            <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-muted">From date</span>
            <input className="input" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          </label>
          <label className="block">
            <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-muted">To date</span>
            <input className="input" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          </label>
          <div>
            <span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-muted">Team / employee</span>
            <RemoteSelect lookup="employees" value={team} onChange={setTeam} placeholder="All teams" />
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5 border-t border-line px-5 py-3">
          <button type="button" className={!activeReport ? 'btn-primary' : 'btn-secondary'} onClick={() => setReport('')}>
            All 16 reports
          </button>
          {REPORT_DEFINITIONS.map((report) => (
            <button
              key={report.key}
              type="button"
              className={activeReport === report.key ? 'btn-primary' : 'btn-secondary'}
              onClick={() => setReport(report.key)}
            >
              {report.label}
            </button>
          ))}
        </div>
      </SectionCard>
      <div className="space-y-5">
        {visibleReports.map((report) => (
          <div key={report.key} id={`report-${report.key}`}>
            <ReportTable report={report} filters={filters} restricted={restricted} />
          </div>
        ))}
        <button type="button" className="btn-secondary" onClick={() => setShowOperational((current) => !current)}>
          {showOperational ? 'Hide' : 'Show'} operational views
        </button>
        {showOperational && <OperationalReports filters={filters} can={can} />}
      </div>
    </>
  )
}
