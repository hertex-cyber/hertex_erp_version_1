import { useEffect, useState } from 'react'
import { BriefcaseBusiness, Building2, GitBranch, Layers, Network, Plus, Wallet } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { Badge, EmptyState, Modal, PageHeader } from '../../components/ui'
import { DataTable } from '../../components/DataTable'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel, money, today } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

function Tabs({ items, value, onChange }) {
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className={`rounded-xl px-3.5 py-2 text-xs font-bold transition ${
            value === item.key
              ? 'bg-primary text-white shadow-sm'
              : 'border border-line bg-surface text-ink-soft hover:bg-surface-2'
          }`}
          onClick={() => onChange(item.key)}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}

function Panel({ title, description, actions, children }) {
  return (
    <section className="card overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="display text-lg font-semibold text-ink">{title}</h2>
          {description && <p className="mt-1 text-xs text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  )
}

const DIMENSION_CONFIGS = {
  entities: {
    label: 'Legal entities',
    endpoint: '/finance/legal-entities',
    permission: 'finance.legalentity',
    icon: Building2,
    fields: [
      { name: 'code', label: 'Code', required: true },
      { name: 'name', label: 'Legal name', required: true },
      { name: 'gstin', label: 'GSTIN' },
      { name: 'currency', label: 'Currency', default: 'INR', required: true },
      { name: 'is_default', label: 'Default entity', type: 'checkbox', default: false },
    ],
    columns: [
      { key: 'code', label: 'Code' },
      { key: 'name', label: 'Legal entity' },
      { key: 'gstin', label: 'GSTIN' },
      { key: 'currency', label: 'Currency' },
    ],
  },
  branches: {
    label: 'Branches',
    endpoint: '/finance/branches',
    permission: 'finance.branch',
    icon: GitBranch,
    fields: [
      { name: 'code', label: 'Code', required: true },
      { name: 'name', label: 'Branch name', required: true },
      { name: 'legal_entity_id', label: 'Legal entity', type: 'reference', lookup: 'legalEntities' },
      { name: 'gstin', label: 'GSTIN' },
      { name: 'parent_id', label: 'Parent branch', type: 'reference', lookup: 'financeBranches' },
    ],
    columns: [
      { key: 'code', label: 'Code' },
      { key: 'name', label: 'Branch' },
      { key: 'legal_entity_id', label: 'Legal entity', render: (row) => <span className="font-mono text-[11px]">{row.legal_entity_id?.slice(0, 8) ?? '—'}</span> },
      { key: 'gstin', label: 'GSTIN' },
    ],
  },
  costCenters: {
    label: 'Cost centers',
    endpoint: '/finance/cost-centers',
    permission: 'finance.costcenter',
    icon: Layers,
    fields: [
      { name: 'code', label: 'Code', required: true },
      { name: 'name', label: 'Cost center', required: true },
      { name: 'legal_entity_id', label: 'Legal entity', type: 'reference', lookup: 'legalEntities' },
      { name: 'parent_id', label: 'Parent cost center', type: 'reference', lookup: 'costCenters' },
    ],
    columns: [
      { key: 'code', label: 'Code' },
      { key: 'name', label: 'Cost center' },
      { key: 'legal_entity_id', label: 'Legal entity', render: (row) => <span className="font-mono text-[11px]">{row.legal_entity_id?.slice(0, 8) ?? '—'}</span> },
    ],
  },
  departments: {
    label: 'Finance departments',
    endpoint: '/finance/departments',
    permission: 'finance.department',
    icon: BriefcaseBusiness,
    fields: [
      { name: 'code', label: 'Code', required: true },
      { name: 'name', label: 'Department', required: true },
      { name: 'legal_entity_id', label: 'Legal entity', type: 'reference', lookup: 'legalEntities' },
      { name: 'parent_id', label: 'Parent department', type: 'reference', lookup: 'financeDepartments' },
    ],
    columns: [
      { key: 'code', label: 'Code' },
      { key: 'name', label: 'Department' },
      { key: 'legal_entity_id', label: 'Legal entity', render: (row) => <span className="font-mono text-[11px]">{row.legal_entity_id?.slice(0, 8) ?? '—'}</span> },
    ],
  },
}

export function DimensionsPage() {
  const [tab, setTab] = useState('entities')
  const config = DIMENSION_CONFIGS[tab]

  return (
    <>
      <PageHeader
        eyebrow="Finance · Dimensions"
        title="Accounting dimensions"
        description="Maintain the legal entities, branches, cost centers and departments used on ledger lines and reports."
      />
      <Tabs
        items={Object.entries(DIMENSION_CONFIGS).map(([key, item]) => ({ key, label: item.label }))}
        value={tab}
        onChange={setTab}
      />
      <ResourcePage
        key={tab}
        eyebrow="Finance · Dimensions"
        title={config.label}
        description="Records are tenant-scoped and available to journals, budgets and dimensional reports."
        endpoint={config.endpoint}
        permission={config.permission}
        createLabel={`New ${config.label.replace(/s$/, '').toLowerCase()}`}
        searchPlaceholder={`Search ${config.label.toLowerCase()}…`}
        columns={config.columns}
        fields={config.fields}
      />
    </>
  )
}

export function ConsolidationPage() {
  const can = useAuth((state) => state.can)
  const [tab, setTab] = useState('transactions')
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (tab !== 'report') return undefined
    let active = true
    setLoading(true)
    api
      .get('/finance/reports/consolidation')
      .then(({ data }) => active && setReport(data))
      .catch((error) => toast.error('Could not load consolidation report', apiErrorMessage(error)))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [tab])

  const action = async (row, kind, reload) => {
    try {
      await api.post(`/finance/intercompany/${row.id}/${kind}`)
      toast.success(kind === 'post' ? 'Intercompany transaction posted' : 'Intercompany balance eliminated', row.number)
      reload()
    } catch (error) {
      toast.error(`Could not ${kind} transaction`, apiErrorMessage(error))
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Finance · Consolidation"
        title="Multi-entity consolidation"
        description="Post intercompany charges, eliminate balances, and review group-level ledger totals."
      />
      <Tabs
        items={[
          { key: 'transactions', label: 'Intercompany' },
          { key: 'report', label: 'Group report' },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === 'transactions' && (
        <ResourcePage
          eyebrow="Finance · Consolidation"
          title="Intercompany transactions"
          description="Posting creates reciprocal AR/AP journals; elimination removes the group balance."
          endpoint="/finance/intercompany"
          permission="finance.intercompany"
          createLabel="New intercompany transaction"
          searchPlaceholder="Search intercompany transactions…"
          columns={[
            { key: 'number', label: 'Number' },
            { key: 'from_entity_id', label: 'From', render: (row) => <span className="font-mono text-[11px]">{row.from_entity_id?.slice(0, 8)}</span> },
            { key: 'to_entity_id', label: 'To', render: (row) => <span className="font-mono text-[11px]">{row.to_entity_id?.slice(0, 8)}</span> },
            { key: 'transaction_date', label: 'Date', render: (row) => dateLabel(row.transaction_date) },
            { key: 'amount', label: 'Amount', align: 'right', render: (row) => money(row.amount, { precise: true }) },
            { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
          ]}
          fields={[
            { name: 'from_entity_id', label: 'From entity', type: 'reference', lookup: 'legalEntities', required: true },
            { name: 'to_entity_id', label: 'To entity', type: 'reference', lookup: 'legalEntities', required: true },
            { name: 'transaction_date', label: 'Transaction date', type: 'date', default: 'today', required: true },
            { name: 'amount', label: 'Amount', type: 'number', required: true },
            { name: 'currency', label: 'Currency', default: 'INR', required: true },
            { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
          ]}
          rowActions={[
            {
              label: 'Post',
              icon: Network,
              show: (row) => row.status === 'draft' && can('finance.intercompany.post'),
              onClick: (row, { reload }) => action(row, 'post', reload),
            },
            {
              label: 'Eliminate',
              icon: Wallet,
              show: (row) => row.status === 'posted' && can('finance.intercompany.eliminate'),
              onClick: (row, { reload }) => action(row, 'eliminate', reload),
            },
          ]}
        />
      )}
      {tab === 'report' && (
        <Panel title="Consolidated position" description="Trial balance totals across all legal entities" actions={loading ? <span className="text-xs text-muted">Loading…</span> : null}>
          {report && (
            <div className="grid gap-4 p-5 sm:grid-cols-3">
              <div className="rounded-xl border border-line bg-surface-2 p-4">
                <p className="text-[11px] font-bold uppercase tracking-wider text-muted">Legal entities</p>
                <p className="display mt-1 text-2xl font-semibold text-ink">{report.legal_entities}</p>
              </div>
              <div className="rounded-xl border border-line bg-surface-2 p-4">
                <p className="text-[11px] font-bold uppercase tracking-wider text-muted">Uneliminated intercompany</p>
                <p className="display mt-1 text-2xl font-semibold text-ink">{money(report.uneliminated_intercompany, { precise: true })}</p>
              </div>
              <div className="rounded-xl border border-line bg-surface-2 p-4">
                <p className="text-[11px] font-bold uppercase tracking-wider text-muted">Source</p>
                <p className="display mt-1 text-lg font-semibold text-ink">{report.source}</p>
              </div>
              <div className="sm:col-span-3">
                <DataTable
                  columns={[
                    { key: 'code', label: 'Account' },
                    { key: 'name', label: 'Name' },
                    { key: 'balance', label: 'Balance', align: 'right', render: (row) => money(row.balance, { precise: true }) },
                  ]}
                  rows={report.trial_balance ?? []}
                  loading={loading}
                  empty={<EmptyState icon={Network} title="No posted balances yet" compact />}
                />
              </div>
            </div>
          )}
        </Panel>
      )}
    </>
  )
}

export function FinanceBudgetsPage() {
  const can = useAuth((state) => state.can)
  const [target, setTarget] = useState(null)
  const [lines, setLines] = useState([])
  const [actuals, setActuals] = useState([])
  const [loading, setLoading] = useState(false)
  const [accountId, setAccountId] = useState('')
  const [period, setPeriod] = useState(today().slice(0, 7))
  const [amount, setAmount] = useState('0.00')
  const [busy, setBusy] = useState(false)

  const loadDetail = async (budget) => {
    setTarget(budget)
    setLoading(true)
    try {
      const [lineData, actualData] = await Promise.all([
        api.get(`/finance/budgets/${budget.id}/lines`),
        api.get(`/finance/budgets/${budget.id}/vs-actual`),
      ])
      setLines(lineData.data ?? [])
      setActuals(actualData.data ?? [])
    } catch (error) {
      toast.error('Could not load budget detail', apiErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  const addLine = async () => {
    if (!target || !accountId || !period) return
    setBusy(true)
    try {
      await api.post(`/finance/budgets/${target.id}/lines`, {
        account_id: accountId,
        period,
        amount,
      })
      toast.success('Budget line added', `${period} · ${money(amount, { precise: true })}`)
      setAccountId('')
      await loadDetail(target)
    } catch (error) {
      toast.error('Could not add budget line', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const activate = async (row, reload) => {
    try {
      await api.post(`/finance/budgets/${row.id}/activate`)
      toast.success('Budget activated', row.name)
      reload()
    } catch (error) {
      toast.error('Could not activate budget', apiErrorMessage(error))
    }
  }

  return (
    <>
      <ResourcePage
        eyebrow="Finance · Planning"
        title="Financial budgets"
        description="Set account-level budgets by period and compare them with posted actuals."
        endpoint="/finance/budgets"
        permission="finance.budget"
        createLabel="New budget"
        searchPlaceholder="Search budgets…"
        columns={[
          { key: 'name', label: 'Budget' },
          { key: 'start_date', label: 'From', render: (row) => dateLabel(row.start_date) },
          { key: 'end_date', label: 'To', render: (row) => dateLabel(row.end_date) },
          { key: 'branch_id', label: 'Branch', render: (row) => <span className="font-mono text-[11px]">{row.branch_id?.slice(0, 8) ?? 'All'}</span> },
          { key: 'cost_center_id', label: 'Cost center', render: (row) => <span className="font-mono text-[11px]">{row.cost_center_id?.slice(0, 8) ?? 'All'}</span> },
          { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
        ]}
        fields={[
          { name: 'name', label: 'Budget name', required: true },
          { name: 'start_date', label: 'Start date', type: 'date', required: true },
          { name: 'end_date', label: 'End date', type: 'date', required: true },
          { name: 'branch_id', label: 'Branch', type: 'reference', lookup: 'financeBranches' },
          { name: 'cost_center_id', label: 'Cost center', type: 'reference', lookup: 'costCenters' },
        ]}
        rowActions={[
          {
            label: 'Details',
            icon: Plus,
            onClick: (row) => loadDetail(row),
          },
          {
            label: 'Activate',
            icon: Wallet,
            show: (row) => row.status === 'draft' && can('finance.budget.activate'),
            onClick: (row, { reload }) => activate(row, reload),
          },
        ]}
      />
      <Modal
        open={Boolean(target)}
        onClose={() => !busy && setTarget(null)}
        title={target ? `${target.name} · ${target.status}` : 'Budget'}
        description="Add account-period amounts and review variance against posted ledger balances."
        size="lg"
        footer={
          <button type="button" className="btn-secondary" onClick={() => setTarget(null)} disabled={busy}>
            Close
          </button>
        }
      >
        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-[1fr_140px_140px_auto]">
            <RemoteAccount value={accountId} onChange={setAccountId} />
            <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
              Period
              <input className="input" placeholder="YYYY-MM" value={period} onChange={(event) => setPeriod(event.target.value)} />
            </label>
            <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
              Amount
              <input className="input" type="number" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} />
            </label>
            <div className="flex items-end">
              <button type="button" className="btn-primary w-full" onClick={addLine} disabled={busy || !accountId || !period}>
                <Plus size={15} /> Add line
              </button>
            </div>
          </div>
          {loading ? (
            <p className="py-6 text-center text-xs text-muted">Loading budget detail…</p>
          ) : (
            <>
              <DataTable
                columns={[
                  { key: 'period', label: 'Period' },
                  { key: 'account_id', label: 'Account', render: (row) => <span className="font-mono text-[11px]">{row.account_id?.slice(0, 8)}</span> },
                  { key: 'amount', label: 'Budget', align: 'right', render: (row) => money(row.amount, { precise: true }) },
                ]}
                rows={lines}
                loading={false}
                empty={<EmptyState icon={Wallet} title="No budget lines yet" compact />}
              />
              <DataTable
                columns={[
                  { key: 'period', label: 'Period' },
                  { key: 'account_code', label: 'Account' },
                  { key: 'budget', label: 'Budget', align: 'right', render: (row) => money(row.budget, { precise: true }) },
                  { key: 'actual', label: 'Actual', align: 'right', render: (row) => money(row.actual, { precise: true }) },
                  { key: 'variance', label: 'Variance', align: 'right', render: (row) => money(row.variance, { precise: true }) },
                ]}
                rows={actuals}
                loading={false}
                empty={<EmptyState icon={Wallet} title="No actuals for this budget" compact />}
              />
            </>
          )}
        </div>
      </Modal>
    </>
  )
}

function RemoteAccount({ value, onChange }) {
  const [options, setOptions] = useState([])

  useEffect(() => {
    let active = true
    api
      .get('/finance/accounts', { params: { size: 200 } })
      .then(({ data }) => active && setOptions(data.items ?? []))
      .catch(() => active && setOptions([]))
    return () => {
      active = false
    }
  }, [])

  return (
    <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
      Account
      <select className="input" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Select account</option>
        {options.map((account) => (
          <option key={account.id} value={account.id}>
            {account.code} · {account.name}
          </option>
        ))}
      </select>
    </label>
  )
}
