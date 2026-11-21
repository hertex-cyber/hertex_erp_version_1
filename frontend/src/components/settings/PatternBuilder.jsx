import { useEffect, useState } from 'react'
import { api, apiErrorMessage } from '../../lib/api'
import { cn } from '../../lib/format'

export const PATTERN_TOKENS = ['{doc}', '{fy}', '{yy}', '{yyyy}', '{mm}', '{dd}', '{seq:05}', '{branch}', '{state}', '{tenant_code}', '{prefix}', '{suffix}']
export const DOC_TYPES = ['internal', 'journal_entry', 'gst_invoice', 'gst_credit_note', 'gst_debit_note', 'gst_bill_of_supply', 'pos_sale']

export function formFromSequence(sequence) {
  return {
    key: sequence?.key ?? '',
    doc_type: sequence?.doc_type ?? 'internal',
    owner_module: sequence?.owner_module ?? 'general',
    pattern: sequence?.pattern ?? '',
    prefix: sequence?.prefix ?? 'DOC',
    suffix: sequence?.suffix ?? '',
    padding: sequence?.padding ?? 5,
    max_length: sequence?.max_length ?? null,
    irp_safe: Boolean(sequence?.irp_safe),
  }
}

export default function PatternBuilder({ sequence, onChange, locked = false, showKey = true }) {
  const [form, setForm] = useState(() => formFromSequence(sequence))
  const [validation, setValidation] = useState(null)
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setForm(formFromSequence(sequence))
  }, [sequence?.id, sequence?.key])

  useEffect(() => {
    onChange?.(form)
  }, [form])

  useEffect(() => {
    let active = true
    const timer = setTimeout(() => {
      api
        .post('/settings/sequences/validate', { ...form, key: form.key || 'preview' })
        .then((response) => {
          if (!active) return
          setValidation(response.data)
          setError('')
          if (!form.key) setPreview(response.data?.sample ?? null)
        })
        .catch((err) => {
          if (active) setError(apiErrorMessage(err, 'Pattern validation is unavailable.'))
        })
    }, 300)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [form.pattern, form.doc_type, form.padding, form.prefix, form.suffix, form.max_length, form.irp_safe])

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function refreshPreview() {
    setError('')
    if (!form.key) {
      setPreview(validation?.sample ?? null)
      return
    }
    try {
      const response = await api.post(`/settings/sequences/${encodeURIComponent(form.key)}/preview`, {})
      setPreview(response.data?.rendered ?? null)
    } catch (err) {
      setError(apiErrorMessage(err, 'Preview is unavailable for this series.'))
      setPreview(validation?.sample ?? null)
    }
  }

  useEffect(() => {
    if (form.key) refreshPreview()
  }, [form.key])

  const gstChannel = String(form.doc_type).startsWith('gst_')
  const problems = validation?.problems ?? []
  const worstCase = validation?.sample ?? null

  return (
    <div className="space-y-4" data-testid="pattern-builder">
      <div className="flex flex-wrap gap-2" data-testid="pattern-tokens">
        {PATTERN_TOKENS.map((token) => (
          <button
            key={token}
            type="button"
            className="rounded-full border border-line bg-surface-2 px-2.5 py-1 font-mono text-[11px] text-ink-soft transition hover:border-primary/40 hover:text-primary"
            data-testid={`pattern-token-${token.replace(/[{}:]/g, '')}`}
            disabled={locked}
            onClick={() => update('pattern', `${form.pattern}${token}`)}
          >
            {token}
          </button>
        ))}
      </div>

      {showKey && (
        <label className="block">
          <span className="label">Series key</span>
          <input className="input" data-testid="pattern-key" value={form.key} disabled={Boolean(sequence) || locked} onChange={(event) => update('key', event.target.value)} placeholder="sales_order" />
        </label>
      )}

      <label className="block">
        <span className="label">Pattern</span>
        <input className="input font-mono" data-testid="pattern-input" value={form.pattern} disabled={locked} onChange={(event) => update('pattern', event.target.value)} placeholder="INV/{fy}/{seq:05}" />
      </label>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <label className="block">
          <span className="label">Document type</span>
          <select className="input" data-testid="pattern-doc-type" value={form.doc_type} disabled={locked} onChange={(event) => update('doc_type', event.target.value)}>
            {DOC_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="label">Padding</span>
          <input className="input" type="number" min={1} max={12} data-testid="pattern-padding" value={form.padding} disabled={locked} onChange={(event) => update('padding', Number(event.target.value))} />
        </label>
        <label className="block">
          <span className="label">Max length</span>
          <input className="input" type="number" min={1} data-testid="pattern-max-length" value={form.max_length ?? ''} disabled={locked} onChange={(event) => update('max_length', event.target.value === '' ? null : Number(event.target.value))} />
        </label>
        <label className="block">
          <span className="label">Prefix</span>
          <input className="input" data-testid="pattern-prefix" value={form.prefix} disabled={locked} onChange={(event) => update('prefix', event.target.value)} />
        </label>
        <label className="block">
          <span className="label">Suffix</span>
          <input className="input" data-testid="pattern-suffix" value={form.suffix} disabled={locked} onChange={(event) => update('suffix', event.target.value)} />
        </label>
        <label className="block">
          <span className="label">Owner module</span>
          <input className="input" data-testid="pattern-owner-module" value={form.owner_module} disabled={locked} onChange={(event) => update('owner_module', event.target.value)} />
        </label>
      </div>

      <label className="flex items-center gap-2 text-sm text-ink-soft">
        <input type="checkbox" data-testid="pattern-irp-safe" checked={form.irp_safe} disabled={locked} onChange={(event) => update('irp_safe', event.target.checked)} />
        IRP-safe (uppercase, no leading 0, - or /)
      </label>

      <div className="rounded-xl border border-line bg-surface-2 p-4" data-testid="pattern-preview-panel">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-muted">Live preview (non-consuming)</p>
            <p className="mt-2 font-mono text-xl font-bold text-primary" data-testid="pattern-preview">{preview || worstCase || '—'}</p>
            {preview && worstCase && preview !== worstCase && <p className="mt-1 text-[11px] text-muted">Worst case: <span className="font-mono">{worstCase}</span></p>}
          </div>
          <button type="button" className="btn-secondary" data-testid="pattern-refresh-preview" onClick={refreshPreview}>Refresh preview</button>
        </div>
      </div>

      {gstChannel && (
        <p className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-700" data-testid="pattern-channel-warning">
          GST documents must be 16 characters or fewer, uppercase A–Z / 0–9 with - or /, unique per financial year, and gaps must carry a reason for GSTR-1.
        </p>
      )}
      {form.irp_safe && (
        <p className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-700" data-testid="pattern-irp-warning">
          IRP rejects lowercase numbers and numbers beginning with 0, - or /. Validation runs against the worst-case pattern.
        </p>
      )}
      {problems.length > 0 && (
        <ul className="space-y-1 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700" data-testid="pattern-validation">
          {problems.map((problem) => <li key={problem}>{problem}</li>)}
        </ul>
      )}
      {validation?.valid && !problems.length && <p className="text-xs font-semibold text-emerald-700" data-testid="pattern-validation">Pattern validated. Worst case fits the document channel.</p>}
      {error && <p className="text-xs text-rose-600">{error}</p>}
    </div>
  )
}
