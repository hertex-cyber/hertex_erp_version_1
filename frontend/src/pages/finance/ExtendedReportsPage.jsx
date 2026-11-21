import { useCallback, useEffect, useState } from 'react'
import { BarChart3, Download, RefreshCw } from 'lucide-react'
import { RemoteSelect } from '../../components/Form'
import { DataTable } from '../../components/DataTable'
import { Badge, EmptyState, PageHeader } from '../../components/ui'
import { Ref } from '../../components/cells'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel, money } from '../../lib/format'
import { toast } from '../../store/toast'

function downloadCsv(filename, columns, rows) {
  const escape = (value) => `"${String(value ?? '').replaceAll('"', '""')}"`
  const header = columns.map((column) => escape(column.label)).join(',')
  const body = rows
    .map((row) => columns.map((column) => escape(column.csv ? column.csv(row) : row[column.key])).join(','))
    .join('\n')
  const url = URL.createObjectURL(new Blob([header, '\n', body].join(''), { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function useReport(endpoint, params = {}, enabled = true) {
  const serialized = JSON.stringify(params)
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)

  const load = useCallback(async () => {
    if (!enabled) return
    setLoading(true)
    try {
      const { data } = await api.get(endpoint, { params })
      setRows(Array.isArray(data) ? data : [data])
      setLoaded(true)
    } catch (error) {
      toast.error('Could not load report', apiErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [endpoint, serialized, enabled])

  useEffect(() => {
    load()
  }, [load])

  return { rows, loading, loaded, reload: load }
}

const TABS = [
  { key: 'ledger', label: 'General ledger' },
  { key: 'dimension', label: 'Dimension ledger' },
  { key: 'payroll', label: 'Payroll cost' },
  { key: 'assets', label: 'Asset register' },
  { key: 'bank', label: 'Bank reconciliation' },
]

export default function ExtendedReportsPage() {
  const [tab, setTab] = useState('ledger')
  const [accountId, setAccountId] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [dimension, setDimension] = useState('cost_center')
  const [period, setPeriod] = useState('')

  const ledger = useReport(
    '/finance/reports/general-ledger',
    { account_id: accountId || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined },
    tab === 'ledger',
  )
  const dimensions = useReport(
    '/finance/reports/dimension',
    { dimension, date_from: dateFrom || undefined, date_to: dateTo || undefined },
    tab === 'dimension',
  )
  const payroll = useReport('/finance/reports/payroll-cost', { period: period || undefined }, tab === 'payroll')
  const assets = useReport('/finance/reports/asset-register', {}, tab === 'assets')
  const bank = useReport('/finance/reports/bank-reconciliation', {}, tab === 'bank')

  const active = {
    ledger,
    dimension: dimensions,
    payroll,
    assets,
    bank,
  }[tab]

  let columns = []
  let title = ''
  let description = ''
  let filename = 'finance-report.csv'

  if (tab === 'ledger') {
    title = 'General ledger'
    description = 'Every posted journal line, filterable by account and posting date.'
    filename = 'general-ledger.csv'
    columns = [
      { key: 'entry_date', label: 'Date', render: (row) => dateLabel(row.entry_date) },
      { key: 'entry_number', label: 'Journal' },
      { key: 'account_code', label: 'Code' },
      { key: 'account_name', label: 'Account' },
      { key: 'description', label: 'Description' },
      { key: 'debit', label: 'Debit', align: 'right', render: (row) => money(row.debit, { precise: true }) },
      { key: 'credit', label: 'Credit', align: 'right', render: (row) => money(row.credit, { precise: true }) },
      { key: 'branch_id', label: 'Branch', render: (row) => <Ref lookup="financeBranches" id={row.branch_id} /> },
      { key: 'cost_center_id', label: 'Cost center', render: (row) => <Ref lookup="costCenters" id={row.cost_center_id} /> },
    ]
  } else if (tab === 'dimension') {
    title = 'Dimension ledger'
    description = 'Debit, credit and net movement grouped by the selected posted-journal dimension.'
    filename = `dimension-${dimension}.csv`
    const lookup = {
      branch: 'financeBranches',
      cost_center: 'costCenters',
      department: 'financeDepartments',
      project: 'projects',
    }[dimension]
    columns = [
      { key: 'dimension_id', label: 'Dimension', render: (row) => <Ref lookup={lookup} id={row.dimension_id} /> },
      { key: 'debit', label: 'Debit', align: 'right', render: (row) => money(row.debit, { precise: true }) },
      { key: 'credit', label: 'Credit', align: 'right', render: (row) => money(row.credit, { precise: true }) },
      { key: 'net', label: 'Net', align: 'right', render: (row) => money(row.net, { precise: true }) },
    ]
  } else if (tab === 'payroll') {
    title = 'Payroll cost'
    description = 'Gross pay and statutory liabilities from processed payroll runs.'
    filename = 'payroll-cost.csv'
    columns = [
      { key: 'period', label: 'Period' },
      { key: 'gross', label: 'Gross', align: 'right', render: (row) => money(row.gross, { precise: true }) },
      { key: 'pf', label: 'PF', align: 'right', render: (row) => money(row.pf, { precise: true }) },
      { key: 'esi', label: 'ESI', align: 'right', render: (row) => money(row.esi, { precise: true }) },
      { key: 'tds', label: 'TDS', align: 'right', render: (row) => money(row.tds, { precise: true }) },
      { key: 'net', label: 'Net', align: 'right', render: (row) => money(row.net, { precise: true }) },
      { key: 'posted', label: 'Posted', render: (row) => <Badge>{row.posted ? 'posted' : 'pending'}</Badge> },
    ]
  } else if (tab === 'assets') {
    title = 'Asset register'
    description = 'Cost, accumulated depreciation and net book value for every registered asset.'
    filename = 'asset-register.csv'
    columns = [
      { key: 'asset_tag', label: 'Tag' },
      { key: 'name', label: 'Asset' },
      { key: 'cost', label: 'Cost', align: 'right', render: (row) => money(row.cost, { precise: true }) },
      { key: 'accumulated_depreciation', label: 'Depreciation', align: 'right', render: (row) => money(row.accumulated_depreciation, { precise: true }) },
      { key: 'net_book_value', label: 'Net book value', align: 'right', render: (row) => money(row.net_book_value, { precise: true }) },
      { key: 'in_service_date', label: 'In service', render: (row) => dateLabel(row.in_service_date) },
      { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
    ]
  } else {
    title = 'Bank reconciliation'
    description = 'Imported bank movement compared with matched ledger movement by account.'
    filename = 'bank-reconciliation.csv'
    columns = [
      { key: 'name', label: 'Bank account' },
      { key: 'opening_balance', label: 'Opening', align: 'right', render: (row) => money(row.opening_balance, { precise: true }) },
      { key: 'bank_movement', label: 'Bank movement', align: 'right', render: (row) => money(row.bank_movement, { precise: true }) },
      { key: 'matched_movement', label: 'Matched', align: 'right', render: (row) => money(row.matched_movement, { precise: true }) },
      { key: 'unmatched_movement', label: 'Unmatched', align: 'right', render: (row) => money(row.unmatched_movement, { precise: true }) },
    ]
  }

  return (
    <>
      <PageHeader
        eyebrow="Finance · Reports"
        title="Extended financial reports"
        description="Ledger-derived reports for general ledger, dimensions, payroll, assets, and bank reconciliation."
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={active.reload} disabled={active.loading}>
              <RefreshCw size={15} className={active.loading ? 'animate-spin' : ''} /> Refresh
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => downloadCsv(filename, columns, active.rows)}
              disabled={!active.rows.length}
            >
              <Download size={15} /> Export
            </button>
          </>
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`rounded-xl px-3.5 py-2 text-xs font-bold transition ${
              tab === item.key
                ? 'bg-primary text-white shadow-sm'
                : 'border border-line bg-surface text-ink-soft hover:bg-surface-2'
            }`}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {(tab === 'ledger' || tab === 'dimension') && (
        <div className="card mb-4 grid gap-4 p-5 sm:grid-cols-3">
          {tab === 'ledger' && (
            <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
              Account
              <RemoteSelect lookup="accounts" value={accountId} onChange={setAccountId} placeholder="All accounts" />
            </label>
          )}
          {tab === 'dimension' && (
            <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
              Dimension
              <select className="input" value={dimension} onChange={(event) => setDimension(event.target.value)}>
                <option value="branch">Branch</option>
                <option value="cost_center">Cost center</option>
                <option value="department">Department</option>
                <option value="project">Project</option>
              </select>
            </label>
          )}
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            From
            <input className="input" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
          </label>
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            To
            <input className="input" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
          </label>
        </div>
      )}
      {tab === 'payroll' && (
        <div className="card mb-4 grid gap-4 p-5 sm:grid-cols-3">
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Payroll period
            <input className="input" placeholder="YYYY-MM" value={period} onChange={(event) => setPeriod(event.target.value)} />
          </label>
        </div>
      )}
      <section className="card overflow-hidden">
        <div className="border-b border-line px-5 py-4">
          <h2 className="display text-lg font-semibold text-ink">{title}</h2>
          <p className="mt-1 text-xs text-muted">{description}</p>
        </div>
        <DataTable
          columns={columns}
          rows={active.rows}
          loading={active.loading}
          empty={<EmptyState icon={BarChart3} title={active.loaded ? 'No report rows' : 'Choose filters and load the report'} compact />}
        />
      </section>
    </>
  )
}
