import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { History, KeyRound, LockKeyhole, RotateCw } from 'lucide-react'
import { api, apiErrorMessage } from '../../lib/api'
import { Modal, PageHeader, LoadingBlock } from '../../components/ui'
import { Status } from '../../components/cells'
import { dateTimeLabel } from '../../lib/format'
import { toast } from '../../store/toast'
import SettingsSubnav from '../../components/settings/SettingsSubnav'

function SecretModal({ action, secret, descriptor, onClose, onDone }) {
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const [windowHours, setWindowHours] = useState(72)
  const [keyVersion, setKeyVersion] = useState(Math.max(1, (secret?.key_version ?? 1) - 1))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const titles = {
    write: 'Write secret',
    rotate: 'Rotate secret',
    rewrap: 'Re-wrap secret',
    revoke: 'Revoke secret',
  }
  const descriptions = {
    write: 'The value is encrypted before storage and never rendered back to the browser.',
    rotate: 'The new value is staged for a dual-control window; commit or rollback afterwards.',
    rewrap: 'Move this secret to a newer key version without changing its plaintext value.',
    revoke: 'Removes the stored secret. Audit history is retained.',
  }

  async function submit() {
    setSaving(true)
    setError('')
    try {
      const key = encodeURIComponent(secret.key)
      if (action === 'write') {
        await api.put(`/settings/secrets/${key}`, { value, reason: reason.trim() || undefined })
      } else if (action === 'rotate') {
        await api.post(`/settings/secrets/${key}/rotate`, { value, window_hours: windowHours })
      } else if (action === 'rewrap') {
        await api.post(`/settings/secrets/${key}/rewrap`, { key_version: keyVersion })
      } else {
        await api.delete(`/settings/secrets/${key}`)
      }
      toast.success(titles[action], `${secret.key} updated.`)
      onDone()
    } catch (err) {
      setError(apiErrorMessage(err, 'The secret could not be updated.'))
    } finally {
      setSaving(false)
    }
  }

  const needsValue = action === 'write' || action === 'rotate'
  const disabled = saving || (needsValue && !value)

  return (
    <Modal
      open
      onClose={onClose}
      title={titles[action]}
      description={descriptions[action]}
      footer={<><button type="button" className="btn-secondary" onClick={onClose}>Cancel</button><button type="button" className="btn-primary" data-testid="secret-action-submit" disabled={disabled} onClick={submit}>{saving ? 'Working…' : titles[action]}</button></>}
    >
      <p className="mb-4 rounded-xl bg-surface-2 p-3 font-mono text-xs text-ink">{secret.key}</p>
      {descriptor?.help && !needsValue && <p className="mb-4 text-xs text-muted">{descriptor.help}</p>}
      {error && <p className="mb-3 text-xs text-rose-600">{error}</p>}
      {needsValue && (
        <label className="block"><span className="label">New value</span><input type="password" autoComplete="new-password" className="input" data-testid="secret-value" value={value} onChange={(event) => setValue(event.target.value)} /></label>
      )}
      {action === 'write' && <label className="mt-3 block"><span className="label">Reason</span><input className="input" data-testid="secret-reason" value={reason} onChange={(event) => setReason(event.target.value)} /></label>}
      {action === 'rotate' && <label className="mt-3 block"><span className="label">Dual-control window (hours)</span><input className="input" type="number" min={1} max={720} data-testid="secret-window" value={windowHours} onChange={(event) => setWindowHours(Number(event.target.value))} /></label>}
      {action === 'rewrap' && <label className="mt-3 block"><span className="label">New key version</span><input className="input" type="number" min={1} data-testid="secret-key-version" value={keyVersion} onChange={(event) => setKeyVersion(Number(event.target.value))} /></label>}
      {action === 'revoke' && <p className="text-sm text-rose-600">This secret will stop working immediately. This cannot be undone from this screen.</p>}
    </Modal>
  )
}

export default function SecretsPage() {
  const navigate = useNavigate()
  const [secrets, setSecrets] = useState([])
  const [descriptors, setDescriptors] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [action, setAction] = useState(null)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const [secretRows, values] = await Promise.all([
        api.get('/settings/secrets'),
        api.get('/settings/values', { params: { size: 500 } }),
      ])
      setSecrets(Array.isArray(secretRows.data) ? secretRows.data : [])
      setDescriptors(Object.fromEntries((values.data?.items ?? []).filter((row) => row.is_secret).map((row) => [row.key, row])))
    } catch (err) {
      setError(apiErrorMessage(err, 'Secrets could not be loaded.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  async function quickAction(secret, operation) {
    setError('')
    try {
      await api.post(`/settings/secrets/${encodeURIComponent(secret.key)}/${operation}`)
      toast.success('Secret updated', `${secret.key} ${operation}ed.`)
      await load()
    } catch (err) {
      setError(apiErrorMessage(err, `The secret could not be ${operation}ed.`))
    }
  }

  const configured = useMemo(() => secrets.filter((row) => row.configured).length, [secrets])

  return (
    <div data-testid="secrets-page">
      <SettingsSubnav />
      <PageHeader
        eyebrow="Settings"
        title="Secrets"
        description="Write-only credentials with masking, dual-control rotation and a complete audit trail."
      />
      <div className="card mb-4 flex flex-wrap items-center justify-between gap-2 p-4">
        <p className="text-sm text-ink-soft"><strong>{configured}</strong> of <strong>{secrets.length}</strong> registered secrets configured</p>
        <p className="flex items-center gap-1.5 text-[11px] font-semibold text-muted"><LockKeyhole size={14} /> Values are encrypted at rest and never displayed after write.</p>
      </div>
      {error && <p className="card mb-4 p-4 text-sm text-rose-600">{error}</p>}
      {loading && <LoadingBlock label="Loading secrets…" />}
      {!loading && (
        <div className="card hidden overflow-x-auto md:block" data-testid="secrets-table">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="bg-surface-2 text-left text-xs text-muted"><tr><th className="th">Secret</th><th className="th">Value</th><th className="th">Status</th><th className="th">Version</th><th className="th">Rotated</th><th className="th">Actions</th></tr></thead>
            <tbody>
              {secrets.map((secret) => (
                <tr key={secret.key} className="border-t" data-testid={`secret-row-${secret.key}`}>
                  <td className="td"><span className="font-semibold text-ink">{descriptors[secret.key]?.label ?? secret.key}</span><span className="mt-0.5 block break-all font-mono text-[10px] text-muted">{secret.key}</span></td>
                  <td className="td"><span className="rounded bg-surface-2 px-2 py-1 font-mono text-xs" data-testid={`secret-mask-${secret.key}`}>{secret.configured ? secret.mask : 'Not configured'}</span></td>
                  <td className="td"><Status value={secret.status} /></td>
                  <td className="td tabular-nums">v{secret.key_version} · {secret.algo}</td>
                  <td className="td">{dateTimeLabel(secret.rotated_at)}</td>
                  <td className="td"><SecretActions secret={secret} setAction={setAction} quickAction={quickAction} navigate={navigate} /></td>
                </tr>
              ))}
              {!secrets.length && <tr><td className="td text-muted" colSpan={6}>No registered secrets are visible with your permissions.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {!loading && (
        <div className="space-y-3 md:hidden" data-testid="secret-cards">
          {secrets.map((secret) => (
            <article key={secret.key} className="card p-4" data-testid={`secret-card-${secret.key}`}>
              <div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="font-semibold text-ink">{descriptors[secret.key]?.label ?? secret.key}</p><p className="break-all font-mono text-[10px] text-muted">{secret.key}</p></div><Status value={secret.status} /></div>
              <p className="mt-2 font-mono text-xs text-ink-soft">{secret.configured ? secret.mask : 'Not configured'} · v{secret.key_version}</p>
              <div className="mt-3"><SecretActions secret={secret} setAction={setAction} quickAction={quickAction} navigate={navigate} /></div>
            </article>
          ))}
          {!secrets.length && <p className="card p-5 text-sm text-muted">No registered secrets are visible with your permissions.</p>}
        </div>
      )}

      {action && (
        <SecretModal
          action={action.action}
          secret={action.secret}
          descriptor={descriptors[action.secret.key]}
          onClose={() => setAction(null)}
          onDone={() => { setAction(null); load() }}
        />
      )}
    </div>
  )
}

function SecretActions({ secret, setAction, quickAction, navigate }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`secret-write-${secret.key}`} onClick={() => setAction({ action: 'write', secret })}><KeyRound size={13} /> Write</button>
      <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`secret-rotate-${secret.key}`} onClick={() => setAction({ action: 'rotate', secret })}><RotateCw size={13} /> Rotate</button>
      {['pending', 'rotating'].includes(secret.status) && (
        <>
          <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`secret-commit-${secret.key}`} onClick={() => quickAction(secret, 'commit')}>Commit</button>
          <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`secret-rollback-${secret.key}`} onClick={() => quickAction(secret, 'rollback')}>Rollback</button>
        </>
      )}
      <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`secret-rewrap-${secret.key}`} onClick={() => setAction({ action: 'rewrap', secret })}>Re-wrap</button>
      <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`secret-history-${secret.key}`} onClick={() => navigate(`/settings/history?entity=secrets&key=${encodeURIComponent(secret.key)}`)}><History size={13} /> History</button>
      <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs text-rose-600" data-testid={`secret-revoke-${secret.key}`} onClick={() => setAction({ action: 'revoke', secret })}>Revoke</button>
    </div>
  )
}
