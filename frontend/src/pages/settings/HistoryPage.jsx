import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, apiErrorMessage } from '../../lib/api'
import { PageHeader, LoadingBlock } from '../../components/ui'
import { Status } from '../../components/cells'
import { dateTimeLabel } from '../../lib/format'
import { toast } from '../../store/toast'
import SettingsSubnav from '../../components/settings/SettingsSubnav'
import CsvExportButton from '../../components/settings/CsvExportButton'
import { formatActor, formatSettingValue } from '../../components/settings/formatters'

const CSV_COLUMNS = [
  { key: 'timestamp', label: 'Time' },
  { key: 'source', label: 'Source' },
  { key: 'action', label: 'Action' },
  { key: 'key', label: 'Key' },
  { key: 'actor', label: 'Actor' },
  { key: 'before', label: 'Before', value: (row) => formatSettingValue(row.before) },
  { key: 'after', label: 'After', value: (row) => formatSettingValue(row.after) },
  { key: 'reason', label: 'Reason' },
  { key: 'approval', label: 'Approval' },
]

function normalizeChange(row) {
  return {
    id: row.id,
    source: 'change',
    action: row.change_type || 'setting.write',
    key: row.key,
    actor: formatActor(row),
    timestamp: row.created_at,
    before: row.old_value,
    after: row.new_value,
    reason: row.reason,
    approval: row.approval_state || 'none',
    raw: row,
  }
}

function normalizeAudit(row) {
  const changes = row.changes ?? {}
  return {
    id: row.id,
    source: 'audit',
    action: row.action,
    key: changes.key || row.entity_id || row.entity,
    actor: formatActor(row),
    timestamp: row.created_at,
    before: changes.old_value ?? changes.before ?? changes.previous_mask,
    after: changes.new_value ?? changes.after ?? changes.mask,
    reason: changes.reason ?? (changes.window_hours ? `window_hours=${changes.window_hours}` : ''),
    approval: changes.approval_state || 'none',
    raw: row,
  }
}

export default function HistoryPage() {
  const [params, setParams] = useSearchParams()
  const keyFilter = params.get('key') ?? ''
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [source, setSource] = useState('all')
  const [action, setAction] = useState('all')
  const [approval, setApproval] = useState('all')
  const [query, setQuery] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [changes, audit] = await Promise.all([
        api.get('/settings/changes', { params: { limit: 200 } }),
        api.get('/system/audit-logs', { params: { module: 'settings', size: 200 } }),
      ])
      setRows([
        ...(Array.isArray(changes.data) ? changes.data : []).map(normalizeChange),
        ...(audit.data?.items ?? []).map(normalizeAudit),
      ].sort((a, b) => new Date(b.timestamp ?? 0) - new Date(a.timestamp ?? 0)))
    } catch (err) {
      setError(apiErrorMessage(err, 'Change history could not be loaded.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const actions = useMemo(() => ['all', ...Array.from(new Set(rows.map((row) => row.action).filter(Boolean))).sort()], [rows])

  const visible = useMemo(() => rows.filter((row) => {
    if (source !== 'all' && row.source !== source) return false
    if (action !== 'all' && row.action !== action) return false
    if (approval !== 'all' && row.approval !== approval) return false
    if (keyFilter && !String(row.key ?? '').toLowerCase().includes(keyFilter.toLowerCase())) return false
    if (from && new Date(row.timestamp ?? 0) < new Date(`${from}T00:00:00`)) return false
    if (to && new Date(row.timestamp ?? 0) > new Date(`${to}T23:59:59`)) return false
    const needle = query.trim().toLowerCase()
    if (!needle) return true
    return `${row.action} ${row.key} ${row.actor} ${row.reason}`.toLowerCase().includes(needle)
  }), [rows, source, action, approval, keyFilter, query, from, to])

  async function decide(row, operation) {
    setError('')
    try {
      await api.post(`/settings/changes/${row.id}/${operation}`)
      toast.success(operation === 'approve' ? 'Change approved' : 'Change rejected', row.key)
      await load()
    } catch (err) {
      setError(apiErrorMessage(err, `The change could not be ${operation}d.`))
    }
  }

  function updateKeyFilter(value) {
    const next = new URLSearchParams(params)
    if (value) next.set('key', value)
    else next.delete('key')
    setParams(next, { replace: true })
  }

  return (
    <div data-testid="history-page">
      <SettingsSubnav />
      <PageHeader
        eyebrow="Settings"
        title="Change history"
        description="Settings changes, secret rotations and audit records in one tamper-evident timeline."
        actions={
          <CsvExportButton
            filename="settings-change-history.csv"
            rows={visible}
            columns={CSV_COLUMNS}
            label="Export history CSV"
            testId="history-csv-export"
          />
        }
      />
      <div className="card mb-4 grid gap-2 p-4 sm:grid-cols-2 xl:grid-cols-3">
        <input className="input" data-testid="history-key-filter" value={keyFilter} onChange={(event) => updateKeyFilter(event.target.value)} placeholder="Filter by key" />
        <input className="input" data-testid="history-query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search actor, action or reason" />
        <select className="input" data-testid="history-source" value={source} onChange={(event) => setSource(event.target.value)}>
          <option value="all">All sources</option><option value="change">Setting changes</option><option value="audit">Audit records</option>
        </select>
        <select className="input" data-testid="history-action" value={action} onChange={(event) => setAction(event.target.value)}>
          {actions.map((value) => <option key={value} value={value}>{value === 'all' ? 'All actions' : value}</option>)}
        </select>
        <select className="input" data-testid="history-approval" value={approval} onChange={(event) => setApproval(event.target.value)}>
          <option value="all">All approvals</option><option value="none">No approval needed</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option>
        </select>
        <div className="grid grid-cols-2 gap-2">
          <input className="input" type="date" data-testid="history-from" value={from} onChange={(event) => setFrom(event.target.value)} aria-label="From date" />
          <input className="input" type="date" data-testid="history-to" value={to} onChange={(event) => setTo(event.target.value)} aria-label="To date" />
        </div>
      </div>
      {error && <p className="card mb-4 p-4 text-sm text-rose-600">{error}</p>}
      {loading && <LoadingBlock label="Loading change history…" />}
      {!loading && (
        <div className="space-y-3" data-testid="history-timeline">
          {visible.map((row) => (
            <article key={`${row.source}-${row.id ?? row.timestamp}`} className="card p-4 sm:p-5" data-testid={`history-row-${row.id ?? row.key}`} data-action={row.action}>
              <div className="flex flex-wrap items-center gap-2 text-[11px] font-bold text-muted">
                <span className="rounded-full bg-primary-soft px-2 py-0.5 text-primary">{row.action}</span>
                <span>{dateTimeLabel(row.timestamp)}</span>
                <span className="rounded-full bg-surface-2 px-2 py-0.5">{row.source}</span>
                <span className="rounded-full bg-surface-2 px-2 py-0.5">{row.approval}</span>
                <Status value={row.approval === 'pending' ? 'pending' : row.approval === 'rejected' ? 'rejected' : row.approval === 'approved' ? 'approved' : 'complete'} />
              </div>
              <p className="mt-3 break-all font-mono text-xs font-bold text-ink">{row.key || '—'}</p>
              <p className="mt-2 break-words font-mono text-xs text-ink-soft">
                <span className="text-muted">{formatSettingValue(row.before)}</span>
                <span className="mx-2 text-primary">→</span>
                <span className="font-bold text-ink">{formatSettingValue(row.after)}</span>
              </p>
              <p className="mt-2 text-xs text-muted">By {row.actor}</p>
              {row.reason && <p className="mt-1 text-xs italic text-ink-soft">“{row.reason}”</p>}
              {row.approval === 'pending' && row.id && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <button type="button" className="btn-primary px-3 py-1.5 text-xs" data-testid={`approve-${row.id}`} onClick={() => decide(row, 'approve')}>Approve</button>
                  <button type="button" className="btn-secondary px-3 py-1.5 text-xs" data-testid={`reject-${row.id}`} onClick={() => decide(row, 'reject')}>Reject</button>
                </div>
              )}
            </article>
          ))}
          {!visible.length && <p className="card p-5 text-sm text-muted">No history matches these filters.</p>}
        </div>
      )}
    </div>
  )
}
