import { useEffect, useRef, useState } from 'react'
import { History, RotateCcw, TriangleAlert } from 'lucide-react'
import { api, apiErrorMessage } from '../../lib/api'
import { titleCase } from '../../lib/format'
import { toast } from '../../store/toast'
import ProvenanceBadge from './ProvenanceBadge'
import SettingHistoryDrawer from './SettingHistoryDrawer'
import { formatSettingValue } from './formatters'

function parseDraft(type, draft) {
  if (type === 'json') {
    try {
      return { value: JSON.parse(draft), error: '' }
    } catch {
      return { value: undefined, error: 'Enter valid JSON.' }
    }
  }
  if (type === 'int') {
    const value = Number(draft)
    return Number.isInteger(value) ? { value, error: '' } : { value: undefined, error: 'Enter a whole number.' }
  }
  if (type === 'decimal' || type === 'currency' || type === 'duration') {
    const value = Number(draft)
    return Number.isFinite(value) && draft !== '' ? { value, error: '' } : { value: undefined, error: 'Enter a number.' }
  }
  return { value: draft, error: '' }
}

function initialDraft(type, value) {
  if (type === 'json') return JSON.stringify(value ?? {}, null, 2)
  return value === null || value === undefined ? '' : String(value)
}

export default function SettingField({ setting, onSaved }) {
  const key = setting?.key
  const [draft, setDraft] = useState(() => initialDraft(setting?.type, setting?.value))
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [state, setState] = useState('')
  const [error, setError] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const acknowledgedState = useRef('')

  useEffect(() => {
    setDraft(initialDraft(setting?.type, setting?.value))
    setReason('')
    setState((current) => (current === acknowledgedState.current ? current : ''))
  }, [setting?.value, setting?.type])

  const locked = Boolean(setting?.deploy_only || setting?.immutable_after || setting?.type === 'secret')
  const critical = Boolean(setting?.critical)
  const parsed = parseDraft(setting?.type, draft)
  const saveDisabled = saving || locked || Boolean(parsed.error) || (critical && !reason.trim())
  const numeric = ['int', 'decimal', 'currency', 'duration'].includes(setting?.type)

  async function save() {
    if (saveDisabled) return
    setSaving(true)
    setError('')
    setState('')
    try {
      const response = await api.put(`/settings/values/${encodeURIComponent(key)}`, {
        value: parsed.value,
        scope: 'tenant',
        reason: reason.trim() || undefined,
        version: setting.stored_version,
      })
      if (response.data.applied === false) {
        acknowledgedState.current = 'Awaiting approval'
        setState('Awaiting approval')
        toast.info('Change submitted for approval', `${key} is waiting for a second approver.`)
      } else {
      acknowledgedState.current = 'Saved'
      setState('Saved')
      toast.success('Setting saved', key)

      }
      setReason('')
      onSaved?.()
    } catch (err) {
      const code = apiErrorMessage(err, 'Unable to save this setting.')
      setError(code)
      toast.error('Setting not saved', code)
    } finally {
      setSaving(false)
    }
  }

  async function reset() {
    if (locked || saving) return
    setSaving(true)
    setError('')
    try {
      await api.delete(`/settings/values/${encodeURIComponent(key)}`, {
        params: { scope: 'tenant', reason: reason.trim() || undefined },
      })
      acknowledgedState.current = 'Reset to default'
      setState('Reset to default')
      setReason('')
      toast.success('Setting reset', `${key} now inherits its default.`)
      onSaved?.()
    } catch (err) {
      setError(apiErrorMessage(err, 'Unable to reset this setting.'))
    } finally {
      setSaving(false)
    }
  }

  let editor = (
    <input
      className="input w-full"
      data-testid={`setting-input-${key}`}
      type={numeric ? 'number' : setting?.type === 'date' ? 'date' : 'text'}
      step={setting?.type === 'int' ? 1 : 'any'}
      min={setting?.min ?? undefined}
      max={setting?.max ?? undefined}
      value={draft}
      disabled={locked}
      onChange={(event) => setDraft(event.target.value)}
    />
  )
  if (setting?.type === 'bool') {
    editor = (
      <label className="flex w-full items-center gap-3 rounded-xl border border-line bg-surface-2 px-3 py-2.5 text-sm text-ink-soft">
        <input
          type="checkbox"
          className="h-4 w-4"
          data-testid={`setting-input-${key}`}
          checked={draft === 'true' || draft === true}
          disabled={locked}
          onChange={(event) => setDraft(String(event.target.checked))}
        />
        Enabled
      </label>
    )
  } else if (setting?.type === 'enum' || setting?.choices?.length) {
    editor = (
      <select
        className="input w-full"
        data-testid={`setting-input-${key}`}
        value={draft}
        disabled={locked}
        onChange={(event) => setDraft(event.target.value)}
      >
        {!setting.choices?.includes(draft) && <option value={draft}>{formatSettingValue(draft)}</option>}
        {(setting.choices ?? []).map((choice) => (
          <option key={choice} value={choice}>{titleCase(choice)}</option>
        ))}
      </select>
    )
  } else if (setting?.type === 'json') {
    editor = (
      <textarea
        className="input min-h-24 w-full font-mono text-xs"
        data-testid={`setting-input-${key}`}
        value={draft}
        disabled={locked}
        onChange={(event) => setDraft(event.target.value)}
      />
    )
  }

  return (
    <article className="card flex h-full flex-col gap-3 p-4 sm:p-5" data-testid={`settings-field-${key}`} data-critical={critical ? 'true' : 'false'}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-ink">{setting?.label || key}</h3>
          <p className="mt-0.5 break-all font-mono text-[10px] text-muted">{key}</p>
        </div>
        <ProvenanceBadge setting={setting} compact />
      </div>

      {setting?.help && <p className="text-xs leading-relaxed text-muted">{setting.help}</p>}
      <div className="flex flex-wrap gap-2 text-[10px] font-semibold text-muted">
        <span className="rounded bg-surface-2 px-2 py-0.5">{setting?.type || 'string'}</span>
        {setting?.choices?.length ? <span className="rounded bg-surface-2 px-2 py-0.5">choices: {setting.choices.join(', ')}</span> : null}
        {setting?.min !== null && setting?.min !== undefined ? <span className="rounded bg-surface-2 px-2 py-0.5">min {setting.min}</span> : null}
        {setting?.max !== null && setting?.max !== undefined ? <span className="rounded bg-surface-2 px-2 py-0.5">max {setting.max}</span> : null}
        {setting?.regex && <span className="rounded bg-surface-2 px-2 py-0.5">pattern: {setting.regex}</span>}
      </div>

      {editor}
      {parsed.error && <p className="text-xs text-rose-600">{parsed.error}</p>}

      {critical && (
        <div className="flex gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-700" data-testid={`setting-critical-${key}`}>
          <TriangleAlert size={15} className="mt-0.5 shrink-0" />
          <span><strong>Critical setting.</strong> Blast radius: this changes behaviour for every new document in this tenant from now on. A reason is required.</span>
        </div>
      )}
      {setting?.deploy_only && <p className="text-xs text-muted">Deploy-only key: owned by the deployment environment and read-only here.</p>}
      {setting?.immutable_after && !setting?.deploy_only && <p className="text-xs text-muted">Locked after {setting.immutable_after}. Create a new legal entity or series instead of changing this value.</p>}

      {!locked && (
        <input
          className="input w-full"
          data-testid={`setting-reason-${key}`}
          value={reason}
          placeholder={critical ? 'Reason required for this critical change' : 'Reason (optional)'}
          onChange={(event) => setReason(event.target.value)}
        />
      )}
      {error && <p className="break-words text-xs text-rose-600" data-testid={`setting-error-${key}`}>{error}</p>}
      {state && <p className="text-xs font-semibold text-emerald-700" data-testid={`setting-state-${key}`}>{state}</p>}

      <div className="mt-auto flex flex-wrap gap-2">
        <button type="button" className="btn-primary flex-1" data-testid={`setting-save-${key}`} disabled={saveDisabled} onClick={save}>
          {saving ? 'Saving…' : 'Save change'}
        </button>
        <button type="button" className="btn-secondary" data-testid={`setting-unset-${key}`} disabled={locked || saving} onClick={reset} title="Reset to the inherited value">
          <RotateCcw size={14} /> Reset
        </button>
        <button type="button" className="btn-secondary" data-testid={`setting-history-${key}`} onClick={() => setHistoryOpen(true)}>
          <History size={14} /> History
        </button>
      </div>

      <SettingHistoryDrawer settingKey={key} open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </article>
  )
}
