import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { api, apiErrorMessage } from '../../lib/api'
import { dateTimeLabel } from '../../lib/format'
import { formatActor, formatSettingValue } from './formatters'

export default function SettingHistoryDrawer({ settingKey, open, onClose }) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open || !settingKey) return undefined
    let active = true
    setLoading(true)
    setError('')
    api
      .get(`/settings/values/${encodeURIComponent(settingKey)}/history`, { params: { limit: 50 } })
      .then((response) => {
        if (active) setRows(Array.isArray(response.data) ? response.data : response.data?.items ?? [])
      })
      .catch((err) => {
        if (active) setError(apiErrorMessage(err, 'History is unavailable for this setting.'))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [open, settingKey])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-forest/60 backdrop-blur-sm" data-testid={`history-drawer-${settingKey}`} role="dialog" aria-modal="true" aria-label={`History for ${settingKey}`}>
      <button type="button" className="absolute inset-0 cursor-default" aria-label="Close history" onClick={onClose} />
      <aside className="animate-in relative flex h-full w-full max-w-xl flex-col border-l border-line bg-surface shadow-[var(--shadow-float)]">
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <p className="eyebrow">Change history</p>
            <h2 className="display mt-1 break-all text-lg font-semibold text-ink">{settingKey}</h2>
          </div>
          <button type="button" className="btn-ghost h-9 w-9 shrink-0 rounded-full px-0" onClick={onClose} aria-label="Close history">
            <X size={17} />
          </button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-5 sm:px-5">
          {loading && <p className="text-sm text-muted">Loading history…</p>}
          {error && <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
          {!loading && !error && !rows.length && <p className="text-sm text-muted">No recorded changes yet. Effective values may come from defaults or deployment configuration.</p>}
          {rows.map((row, index) => (
            <article key={row.id ?? `${row.created_at}-${index}`} className="card p-4" data-testid="history-row">
              <div className="flex flex-wrap items-center gap-2 text-[11px] font-bold text-muted">
                <span className="rounded-full bg-primary-soft px-2 py-0.5 text-primary">{row.change_type || row.action || 'set'}</span>
                <span>{dateTimeLabel(row.created_at)}</span>
                <span className="rounded-full bg-surface-2 px-2 py-0.5">{row.approval_state || 'none'}</span>
              </div>
              <p className="mt-3 break-words font-mono text-xs text-ink-soft">
                <span className="text-muted">{formatSettingValue(row.old_value)}</span>
                <span className="mx-2 text-primary">→</span>
                <span className="font-bold text-ink">{formatSettingValue(row.new_value ?? row.value)}</span>
              </p>
              <p className="mt-2 text-xs text-muted">By {formatActor(row)}</p>
              {row.reason && <p className="mt-1 text-xs italic text-ink-soft">“{row.reason}”</p>}
            </article>
          ))}
        </div>
      </aside>
    </div>
  )
}
