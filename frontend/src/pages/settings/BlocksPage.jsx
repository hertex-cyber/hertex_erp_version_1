import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, apiErrorMessage } from '../../lib/api'
import { Modal, PageHeader, LoadingBlock } from '../../components/ui'
import { Status } from '../../components/cells'
import { dateTimeLabel, num } from '../../lib/format'
import { toast } from '../../store/toast'
import SettingsSubnav from '../../components/settings/SettingsSubnav'
import CsvExportButton from '../../components/settings/CsvExportButton'

const CSV_COLUMNS = [
  { key: 'key', label: 'Series' },
  { key: 'id', label: 'Block' },
  { key: 'device_id', label: 'Device' },
  { key: 'fiscal_year', label: 'Financial year' },
  { key: 'range_start', label: 'From' },
  { key: 'range_end', label: 'To' },
  { key: 'used_count', label: 'Used' },
  { key: 'status', label: 'Status' },
  { key: 'expires_at', label: 'Expires' },
]

export default function BlocksPage() {
  const [params, setParams] = useSearchParams()
  const key = params.get('key') ?? ''
  const [sequences, setSequences] = useState([])
  const [blocks, setBlocks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [issuing, setIssuing] = useState(false)
  const [returning, setReturning] = useState(null)
  const [issueForm, setIssueForm] = useState({ size: 100, device_id: '', expires_in_days: 7 })
  const [usedUpTo, setUsedUpTo] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get('/settings/sequences', { params: { size: 200 } })
      .then((response) => setSequences(response.data?.items ?? []))
      .catch((err) => setError(apiErrorMessage(err, 'Series could not be loaded.')))
  }, [])

  useEffect(() => {
    let active = true
    setError('')
    if (!key) {
      setBlocks([])
      setLoading(false)
      return () => { active = false }
    }
    setLoading(true)
    api.get(`/settings/sequences/${encodeURIComponent(key)}/blocks`)
      .then((response) => {
        if (active) setBlocks(Array.isArray(response.data) ? response.data : [])
      })
      .catch((err) => {
        if (active) setError(apiErrorMessage(err, 'Offline blocks could not be loaded.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [key])

  const csvRows = useMemo(() => blocks.map((block) => ({ key, ...block })), [blocks, key])

  async function issueBlock() {
    if (!key) return
    setSaving(true)
    setError('')
    try {
      await api.post(`/settings/sequences/${encodeURIComponent(key)}/blocks`, issueForm)
      toast.success('Block issued', `${issueForm.size} numbers reserved for ${issueForm.device_id}.`)
      setIssuing(false)
      setIssueForm({ size: 100, device_id: '', expires_in_days: 7 })
      const response = await api.get(`/settings/sequences/${encodeURIComponent(key)}/blocks`)
      setBlocks(response.data ?? [])
    } catch (err) {
      setError(apiErrorMessage(err, 'The block could not be issued.'))
    } finally {
      setSaving(false)
    }
  }

  async function returnBlock() {
    if (!returning) return
    setSaving(true)
    setError('')
    try {
      await api.post(`/settings/blocks/${returning.id}/return`, { used_up_to: usedUpTo === '' ? null : Number(usedUpTo) })
      toast.success('Block returned', 'Unused numbers were returned to the series.')
      setReturning(null)
      setUsedUpTo('')
      const response = await api.get(`/settings/sequences/${encodeURIComponent(key)}/blocks`)
      setBlocks(response.data ?? [])
    } catch (err) {
      setError(apiErrorMessage(err, 'The block could not be returned.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div data-testid="blocks-page">
      <SettingsSubnav />
      <PageHeader
        eyebrow="Settings · Numbering"
        title="Offline blocks"
        description="Reserve ranges for field devices, then return unused numbers so the audit trail stays complete."
        actions={
          <CsvExportButton
            filename={`numbering-blocks-${key || 'all'}.csv`}
            rows={csvRows}
            columns={CSV_COLUMNS}
            label="Export blocks CSV"
            testId="blocks-csv-export"
          />
        }
      />
      <div className="card mb-4 grid gap-2 p-4 sm:grid-cols-[minmax(0,1fr)_auto]">
        <select
          className="input"
          data-testid="block-series-select"
          value={key}
          onChange={(event) => { const next = new URLSearchParams(params); if (event.target.value) next.set('key', event.target.value); else next.delete('key'); setParams(next, { replace: true }) }}
        >
          <option value="">Select a series</option>
          {sequences.map((row) => <option key={row.id} value={row.key}>{row.key}</option>)}
        </select>
        <button type="button" className="btn-primary w-full sm:w-auto" data-testid="issue-block" disabled={!key} onClick={() => setIssuing(true)}>Issue block</button>
      </div>
      {error && <p className="card mb-4 p-4 text-sm text-rose-600">{error}</p>}
      {loading && <LoadingBlock label="Loading blocks…" />}
      {!loading && key && (
        <>
          <div className="card hidden overflow-x-auto md:block" data-testid="blocks-table">
            <table className="w-full min-w-[720px] text-sm">
              <thead className="bg-surface-2 text-left text-xs text-muted"><tr><th className="th">Block</th><th className="th">Device</th><th className="th">Range</th><th className="th">Used</th><th className="th">Status</th><th className="th">Expires</th><th className="th">Action</th></tr></thead>
              <tbody>
                {blocks.map((block) => (
                  <tr key={block.id} className="border-t" data-testid={`block-row-${block.id}`}>
                    <td className="td font-mono text-xs">{String(block.id).slice(0, 8)}</td>
                    <td className="td">{block.device_id}</td>
                    <td className="td tabular-nums">{num(block.range_start)}–{num(block.range_end)}</td>
                    <td className="td tabular-nums">{num(block.used_count)} / {num(block.size)}</td>
                    <td className="td"><Status value={block.expired ? 'expired' : block.status} /></td>
                    <td className="td">{dateTimeLabel(block.expires_at)}</td>
                    <td className="td"><button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`return-block-${block.id}`} disabled={!['issued', 'partially_used'].includes(block.status)} onClick={() => { setReturning(block); setUsedUpTo(String(block.used_count ?? '')) }}>Return</button></td>
                  </tr>
                ))}
                {!blocks.length && <tr><td className="td text-muted" colSpan={7}>No blocks issued for this series.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="space-y-3 md:hidden" data-testid="block-cards">
            {blocks.map((block) => (
              <article key={block.id} className="card p-4" data-testid={`block-card-${block.id}`}>
                <div className="flex items-center justify-between gap-2"><p className="break-all font-mono text-xs text-ink">{String(block.id).slice(0, 8)}</p><Status value={block.expired ? 'expired' : block.status} /></div>
                <p className="mt-2 text-sm text-ink-soft">{block.device_id} · {num(block.range_start)}–{num(block.range_end)}</p>
                <p className="mt-1 text-xs text-muted">{num(block.used_count)} of {num(block.size)} used · expires {dateTimeLabel(block.expires_at)}</p>
                <button type="button" className="btn-secondary mt-3 w-full" data-testid={`return-block-${block.id}`} disabled={!['issued', 'partially_used'].includes(block.status)} onClick={() => { setReturning(block); setUsedUpTo(String(block.used_count ?? '')) }}>Return</button>
              </article>
            ))}
            {!blocks.length && <p className="card p-5 text-sm text-muted">No blocks issued for this series.</p>}
          </div>
        </>
      )}
      {!loading && !key && <p className="card p-5 text-sm text-muted">Choose a series to inspect its offline blocks.</p>}

      <Modal
        open={issuing}
        onClose={() => setIssuing(false)}
        title="Issue offline block"
        description="Numbers are reserved atomically and cannot be allocated elsewhere until returned or expired."
        footer={<><button type="button" className="btn-secondary" onClick={() => setIssuing(false)}>Cancel</button><button type="button" className="btn-primary" data-testid="block-issue-submit" disabled={saving || !issueForm.device_id.trim()} onClick={issueBlock}>{saving ? 'Issuing…' : 'Issue block'}</button></>}
      >
        <label className="block"><span className="label">Device ID</span><input className="input" data-testid="block-device" value={issueForm.device_id} onChange={(event) => setIssueForm((current) => ({ ...current, device_id: event.target.value }))} /></label>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="block"><span className="label">Size</span><input className="input" type="number" min={1} max={500} data-testid="block-size" value={issueForm.size} onChange={(event) => setIssueForm((current) => ({ ...current, size: Number(event.target.value) }))} /></label>
          <label className="block"><span className="label">Expires in days</span><input className="input" type="number" min={1} max={90} data-testid="block-expiry" value={issueForm.expires_in_days} onChange={(event) => setIssueForm((current) => ({ ...current, expires_in_days: Number(event.target.value) }))} /></label>
        </div>
      </Modal>

      <Modal
        open={Boolean(returning)}
        onClose={() => setReturning(null)}
        title="Return block"
        description="Record the highest number used on the device; the remainder returns to the pool."
        footer={<><button type="button" className="btn-secondary" onClick={() => setReturning(null)}>Cancel</button><button type="button" className="btn-primary" data-testid="block-return-submit" disabled={saving} onClick={returnBlock}>{saving ? 'Returning…' : 'Return block'}</button></>}
      >
        <p className="mb-4 text-sm text-ink-soft">{returning?.device_id} · {num(returning?.range_start)}–{num(returning?.range_end)}</p>
        <label className="block"><span className="label">Used up to (optional)</span><input className="input" type="number" data-testid="block-used-up-to" value={usedUpTo} onChange={(event) => setUsedUpTo(event.target.value)} /></label>
      </Modal>
    </div>
  )
}
