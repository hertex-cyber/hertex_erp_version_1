import { useEffect, useState } from 'react'
import { KeyRound, Laptop, ShieldCheck, ShieldOff, Smartphone } from 'lucide-react'
import { api, apiErrorMessage } from '../lib/api'
import { useAuth } from '../store/auth'
import { toast } from '../store/toast'
import { Badge, LoadingBlock, PageHeader, SectionCard, Spinner } from '../components/ui'

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

export default function SecurityPage() {
  const changePassword = useAuth((state) => state.changePassword)
  const [overview, setOverview] = useState(null)
  const [setup, setSetup] = useState(null)
  const [code, setCode] = useState('')
  const [disablePassword, setDisablePassword] = useState('')
  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' })
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  const load = async () => {
    const { data } = await api.get('/auth/security')
    setOverview(data)
  }

  useEffect(() => {
    load().catch((requestError) => setError(apiErrorMessage(requestError)))
  }, [])

  const run = async (key, action, success) => {
    setBusy(key)
    setError('')
    try {
      await action()
      if (success) toast.success(success)
      await load()
    } catch (requestError) {
      setError(apiErrorMessage(requestError))
    } finally {
      setBusy('')
    }
  }

  const startSetup = () => run('setup', async () => {
    const { data } = await api.post('/auth/mfa/setup')
    setSetup(data)
  })

  const enableMfa = () => run('enable', async () => {
    await api.post('/auth/mfa/enable', { code, recovery_codes: setup.recovery_codes })
    setSetup(null)
    setCode('')
  }, 'Two-step verification enabled')

  const disableMfa = () => run('disable', async () => {
    await api.post('/auth/mfa/disable', { password: disablePassword })
    setDisablePassword('')
  }, 'Two-step verification disabled')

  const submitPassword = (event) => {
    event.preventDefault()
    if (passwords.next !== passwords.confirm) {
      setError('New passwords do not match.')
      return
    }
    run('password', async () => {
      await changePassword(passwords.current, passwords.next)
      setPasswords({ current: '', next: '', confirm: '' })
    }, 'Password updated')
  }

  const revoke = (id) => run(`session-${id}`, async () => {
    await api.delete(`/auth/sessions/${id}`)
  }, 'Session revoked')

  const revokeAll = () => run('sessions', async () => {
    await api.delete('/auth/sessions')
  }, 'All other sessions revoked')

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Account"
        title="Security"
        description="Manage your password, two-step verification and active sessions."
      />

      {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-semibold text-rose-700">{error}</div>}

      {!overview ? <LoadingBlock label="Loading security settings…" /> : (
        <>
          <SectionCard title="Password" description={`Minimum ${overview.password_policy.min_length} characters with mixed case, a number and a symbol.`}>
            <form onSubmit={submitPassword} className="grid max-w-3xl gap-4 md:grid-cols-3">
              <div>
                <label className="label">Current password</label>
                <input type="password" className="input" autoComplete="current-password" required value={passwords.current} onChange={(event) => setPasswords({ ...passwords, current: event.target.value })} />
              </div>
              <div>
                <label className="label">New password</label>
                <input type="password" className="input" autoComplete="new-password" required minLength={overview.password_policy.min_length} value={passwords.next} onChange={(event) => setPasswords({ ...passwords, next: event.target.value })} />
              </div>
              <div>
                <label className="label">Confirm password</label>
                <input type="password" className="input" autoComplete="new-password" required minLength={overview.password_policy.min_length} value={passwords.confirm} onChange={(event) => setPasswords({ ...passwords, confirm: event.target.value })} />
              </div>
              <div className="md:col-span-3">
                <button type="submit" className="btn-primary" disabled={busy === 'password'}>
                  {busy === 'password' ? <Spinner className="h-4 w-4" /> : <KeyRound size={15} />}
                  Update password
                </button>
              </div>
            </form>
          </SectionCard>

          <SectionCard
            title="Two-step verification"
            description="Use an authenticator app and keep recovery codes somewhere safe."
            action={overview.mfa.enabled ? <Badge tone="positive">Enabled</Badge> : <Badge tone="neutral">Disabled</Badge>}
          >
            {setup ? (
              <div className="max-w-3xl space-y-4">
                <p className="text-xs leading-relaxed text-muted">Scan this secret in your authenticator app, then enter the 6-digit code to confirm.</p>
                <div className="rounded-xl border border-line bg-surface-2 p-4 font-mono text-sm text-ink">{setup.secret}</div>
                <div className="rounded-xl border border-line bg-surface-2 p-4">
                  <p className="label">Recovery codes</p>
                  <div className="mt-2 grid gap-1 font-mono text-xs text-ink-soft sm:grid-cols-2">
                    {setup.recovery_codes.map((item) => <span key={item}>{item}</span>)}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <input className="input w-40" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} placeholder="000000" value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))} />
                  <button type="button" className="btn-primary" onClick={enableMfa} disabled={busy === 'enable' || code.length !== 6}>
                    {busy === 'enable' ? <Spinner className="h-4 w-4" /> : <ShieldCheck size={15} />}
                    Confirm and enable
                  </button>
                  <button type="button" className="btn-ghost" onClick={() => setSetup(null)}>Cancel</button>
                </div>
              </div>
            ) : overview.mfa.enabled ? (
              <div className="flex max-w-3xl flex-wrap items-center gap-3">
                <input type="password" className="input w-64" placeholder="Confirm password to disable" value={disablePassword} onChange={(event) => setDisablePassword(event.target.value)} />
                <button type="button" className="btn-ghost" onClick={disableMfa} disabled={busy === 'disable' || !disablePassword}>
                  {busy === 'disable' ? <Spinner className="h-4 w-4" /> : <ShieldOff size={15} />}
                  Disable two-step verification
                </button>
              </div>
            ) : (
              <button type="button" className="btn-primary" onClick={startSetup} disabled={busy === 'setup'}>
                {busy === 'setup' ? <Spinner className="h-4 w-4" /> : <Smartphone size={15} />}
                Set up authenticator
              </button>
            )}
          </SectionCard>

          <SectionCard
            title="Active sessions"
            description="Sign out of any device you no longer recognise."
            action={overview.sessions.length > 1 ? <button type="button" className="btn-ghost" onClick={revokeAll} disabled={busy === 'sessions'}>Sign out other sessions</button> : null}
          >
            <div className="divide-y divide-line">
              {overview.sessions.map((session) => (
                <div key={session.id} className="flex flex-wrap items-center gap-4 py-3">
                  <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-surface-2 text-muted"><Laptop size={16} /></span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-ink">{session.device_label ?? 'Unknown device'}</p>
                    <p className="text-[11px] text-muted">{session.ip_address ?? 'Unknown IP'} · Last seen {formatDate(session.last_used_at)} · Expires {formatDate(session.expires_at)}</p>
                  </div>
                  {session.current ? (
                    <Badge tone="positive">Current</Badge>
                  ) : (
                    <button type="button" className="btn-ghost" onClick={() => revoke(session.id)} disabled={busy === `session-${session.id}`}>Revoke</button>
                  )}
                </div>
              ))}
            </div>
            {!overview.sessions.length && <p className="py-6 text-center text-xs text-muted">No active sessions.</p>}
          </SectionCard>
        </>
      )}
    </div>
  )
}
