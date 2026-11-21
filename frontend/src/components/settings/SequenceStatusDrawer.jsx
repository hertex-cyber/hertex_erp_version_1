import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { api, apiErrorMessage } from '../../lib/api'
import { dateTimeLabel, num } from '../../lib/format'

function Stat({ label, value, testId }) {
  return (
    <div className="rounded-xl border border-line bg-surface-2 p-3">
      <p className="text-[10px] font-bold uppercase tracking-wider text-muted">{label}</p>
      <p className="mt-1 font-mono text-base font-bold text-ink" data-testid={testId}>{value ?? '—'}</p>
    </div>
  )
}

export default function SequenceStatusDrawer({ sequenceKey, open, onClose, onViewBlocks }) {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open || !sequenceKey) return undefined
    let active = true
    setLoading(true)
    setError('')
    api
      .get(`/settings/sequences/${encodeURIComponent(sequenceKey)}/status`)
      .then((response) => {
        if (active) setStatus(response.data)
      })
      .catch((err) => {
        if (active) setError(apiErrorMessage(err, 'Status is unavailable for this series.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [open, sequenceKey])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-forest/60 backdrop-blur-sm" data-testid="sequence-status-drawer" role="dialog" aria-modal="true" aria-label={`Status for ${sequenceKey}`}>
      <button type="button" className="absolute inset-0 cursor-default" aria-label="Close status" onClick={onClose} />
      <aside className="animate-in relative flex h-full w-full max-w-lg flex-col overflow-hidden border-l border-line bg-surface shadow-[var(--shadow-float)]">
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <p className="eyebrow">Sequence status</p>
            <h2 className="display mt-1 text-lg font-semibold text-ink">{sequenceKey}</h2>
          </div>
          <button type="button" className="btn-ghost h-9 w-9 rounded-full px-0" onClick={onClose} aria-label="Close status">
            <X size={17} />
          </button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-5">
          {loading && <p className="text-sm text-muted">Loading status…</p>}
          {error && <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
          {status && (
            <>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <Stat label="Financial year" value={status.fiscal_year} testId="status-fy" />
                <Stat label="Next number" value={num(status.next_number)} testId="status-next" />
                <Stat label="Preview" value={status.preview} testId="status-preview" />
                <Stat label="Allocated" value={num(status.allocated_count)} testId="status-allocated" />
                <Stat label="Manual" value={num(status.manual_allocations)} testId="status-manual" />
                <Stat label="Voided" value={num(status.voided_allocations)} testId="status-voided" />
                <Stat label="Period status" value={status.period_status} testId="status-period" />
                <Stat label="Open blocks" value={num(status.open_blocks)} testId="status-blocks" />
                <Stat label="Last allocated" value={dateTimeLabel(status.last_allocated_at)} testId="status-last" />
              </div>
              <div className="rounded-xl border border-line bg-surface-2 p-3 text-xs text-muted">
                <p>{status.doc_type} · {status.owner_module} · {status.implementation} · resets {status.reset_policy}</p>
                {status.period_start && status.period_end && <p className="mt-1">Period {status.period_start} → {status.period_end}</p>}
              </div>
              <button type="button" className="btn-secondary w-full" data-testid="status-view-blocks" onClick={() => onViewBlocks?.(sequenceKey)}>View offline blocks</button>
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
