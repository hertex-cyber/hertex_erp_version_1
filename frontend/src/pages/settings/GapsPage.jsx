import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, apiErrorMessage } from '../../lib/api'
import { PageHeader, LoadingBlock } from '../../components/ui'
import SettingsSubnav from '../../components/settings/SettingsSubnav'
import CsvExportButton from '../../components/settings/CsvExportButton'
import { formatSettingValue } from '../../components/settings/formatters'

const CSV_COLUMNS = [
  { key: 'section', label: 'Section' },
  { key: 'key', label: 'Series' },
  { key: 'fiscal_year', label: 'Financial year' },
  { key: 'rendered', label: 'Number' },
  { key: 'reason_code', label: 'Reason code' },
  { key: 'reason_text', label: 'Reason' },
  { key: 'device_id', label: 'Device' },
  { key: 'status', label: 'Status' },
]

function columnsFor(rows) {
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row ?? {})))).slice(0, 7)
  if (!keys.length) return [{ key: 'key', label: 'Key' }]
  return keys.map((key) => ({ key, label: key.replaceAll('_', ' '), value: (row) => formatSettingValue(row[key]) }))
}

function ReportTable({ title, rows, testId }) {
  const columns = columnsFor(rows)
  return (
    <section className="card overflow-hidden" data-testid={testId}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <h2 className="text-sm font-bold text-ink">{title}</h2>
        <span className="text-xs text-muted">{rows.length} row{rows.length === 1 ? '' : 's'}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[620px] text-sm">
          <thead className="bg-surface-2 text-left text-xs text-muted"><tr>{columns.map((column) => <th className="th" key={column.key}>{column.label}</th>)}</tr></thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={row.id ?? index} className="border-t">
                {columns.map((column) => <td className="td" key={column.key}>{formatSettingValue(row[column.key])}</td>)}
              </tr>
            ))}
            {!rows.length && <tr><td className="td text-muted" colSpan={columns.length}>None recorded.</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default function GapsPage() {
  const [params, setParams] = useSearchParams()
  const sequenceKey = params.get('key') ?? ''
  const [fiscalYear, setFiscalYear] = useState('')
  const [sequences, setSequences] = useState([])
  const [report, setReport] = useState({ unexplained: [], declared: [], unreturned_blocks: [], totals: {} })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/settings/sequences', { params: { size: 200 } })
      .then((response) => setSequences(response.data?.items ?? []))
      .catch(() => setSequences([]))
  }, [])

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    api.get('/settings/reports/numbering/gaps', { params: { key: sequenceKey || undefined, fiscal_year: fiscalYear || undefined } })
      .then((response) => {
        if (active) setReport(response.data ?? {})
      })
      .catch((err) => {
        if (active) setError(apiErrorMessage(err, 'The gap report could not be loaded.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [sequenceKey, fiscalYear])

  const declared = report.declared ?? []
  const unexplained = report.unexplained ?? []
  const blocks = report.unreturned_blocks ?? []
  const csvRows = useMemo(() => [
    ...declared.map((row) => ({ section: 'declared', ...row })),
    ...unexplained.map((row) => ({ section: 'unexplained', ...row })),
    ...blocks.map((row) => ({ section: 'unreturned_blocks', ...row })),
  ], [declared, unexplained, blocks])

  return (
    <div data-testid="gaps-page">
      <SettingsSubnav />
      <PageHeader
        eyebrow="Settings · Numbering"
        title="Numbering gaps"
        description="Every consumed number has a ledger row, and every gap has a reason that can be exported for GSTR-1 reconciliation."
        actions={
          <CsvExportButton
            filename="numbering-gaps.csv"
            rows={csvRows}
            columns={CSV_COLUMNS}
            label="Export gaps CSV"
            testId="gaps-csv-export"
          />
        }
      />
      <div className="card mb-4 grid gap-2 p-4 sm:grid-cols-2">
        <select className="input" data-testid="gap-series-filter" value={sequenceKey} onChange={(event) => { const next = new URLSearchParams(params); if (event.target.value) next.set('key', event.target.value); else next.delete('key'); setParams(next, { replace: true }) }}>
          <option value="">All series</option>
          {sequences.map((row) => <option key={row.id} value={row.key}>{row.key}</option>)}
        </select>
        <input className="input" data-testid="gap-fiscal-filter" value={fiscalYear} onChange={(event) => setFiscalYear(event.target.value)} placeholder="Financial year (e.g. 2025-26)" />
      </div>
      {error && <p className="card mb-4 p-4 text-sm text-rose-600">{error}</p>}
      {loading && <LoadingBlock label="Loading gap report…" />}
      {!loading && (
        <>
          <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4" data-testid="gap-totals">
            {Object.entries(report.totals ?? {}).map(([key, value]) => (
              <div key={key} className="card p-4">
                <p className="text-[10px] font-bold uppercase tracking-wider text-muted">{key.replaceAll('_', ' ')}</p>
                <p className="mt-1 text-lg font-bold text-ink">{formatSettingValue(value)}</p>
              </div>
            ))}
            {!Object.keys(report.totals ?? {}).length && <p className="text-sm text-muted">No totals reported.</p>}
          </div>
          <div className="space-y-4">
            <ReportTable title="Declared gaps" rows={declared} testId="gap-declared" />
            <ReportTable title="Unexplained gaps" rows={unexplained} testId="gap-unexplained" />
            <ReportTable title="Unreturned blocks" rows={blocks} testId="gap-unreturned-blocks" />
          </div>
        </>
      )}
    </div>
  )
}
