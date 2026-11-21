import { useCallback, useEffect, useMemo, useState } from 'react'
import { RefreshCw, ShieldCheck } from 'lucide-react'
import {
  Badge,
  EmptyState,
  Modal,
  PageHeader,
  SectionCard,
  Spinner,
} from '../../components/ui'
import { api, apiErrorMessage } from '../../lib/api'
import { dateTimeLabel, titleCase } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

const TEST_RESULTS_KEY = 'hertex.external-integration-tests'

function readTestResults() {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.sessionStorage.getItem(TEST_RESULTS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export default function ExternalIntegrationsPage() {
  const can = useAuth((state) => state.can)
  const canRead = can('integrations.channel.manage') || can('settings.setting.read')
  const canWrite = can('integrations.channel.manage') || can('system.settings.manage')
  const [providers, setProviders] = useState([])
  const [selected, setSelected] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [testResults, setTestResults] = useState(readTestResults)
  const [testing, setTesting] = useState('')
  const [busyField, setBusyField] = useState('')
  const [editor, setEditor] = useState(null)
  const [secretValue, setSecretValue] = useState('')
  const [reason, setReason] = useState('')
  const [windowHours, setWindowHours] = useState(72)
  const [editorError, setEditorError] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get('/integrations/external/providers')
      const items = Array.isArray(data) ? data : []
      setProviders(items)
      setSelected((current) =>
        items.some((item) => item.provider === current)
          ? current
          : items[0]?.provider ?? '',
      )
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Could not load external providers.'))
      setProviders([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (canRead) load()
  }, [canRead, load])

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.sessionStorage.setItem(TEST_RESULTS_KEY, JSON.stringify(testResults))
    } catch {
      return undefined
    }
    return undefined
  }, [testResults])

  const selectedProvider = useMemo(
    () => providers.find((provider) => provider.provider === selected) ?? null,
    [providers, selected],
  )

  const applyCredential = (providerKey, credential) => {
    setProviders((current) =>
      current.map((provider) => {
        if (provider.provider !== providerKey) return provider
        const credentials = (provider.credentials ?? []).map((item) =>
          item.field === credential.field ? { ...item, ...credential } : item,
        )
        const configuredFields = credentials
          .filter((item) => item.configured)
          .map((item) => item.field)
        const missingFields = (provider.required_fields ?? []).filter(
          (field) => !configuredFields.includes(field),
        )
        return {
          ...provider,
          credentials,
          configured_fields: configuredFields,
          missing_fields: missingFields,
          is_configured: missingFields.length === 0,
        }
      }),
    )
  }

  const openEditor = (mode, field) => {
    setEditor({ mode, field })
    setSecretValue('')
    setReason('')
    setWindowHours(72)
    setEditorError('')
  }

  const closeEditor = () => {
    if (saving) return
    setEditor(null)
    setSecretValue('')
    setReason('')
    setEditorError('')
  }

  const saveCredential = async (event) => {
    event.preventDefault()
    if (!editor || !selectedProvider || !secretValue.trim()) return
    const hours = Number(windowHours)
    if (editor.mode === 'rotate' && (!Number.isInteger(hours) || hours < 1 || hours > 720)) {
      setEditorError('Rotation window must be between 1 and 720 hours.')
      return
    }
    setSaving(true)
    setEditorError('')
    try {
      if (editor.mode === 'set') {
        const payload = {
          credentials: { [editor.field]: secretValue },
          ...(reason.trim() ? { reason: reason.trim() } : {}),
        }
        const { data } = await api.put(
          `/integrations/external/providers/${selectedProvider.provider}/credentials`,
          payload,
        )
        setProviders((current) =>
          current.map((provider) => (provider.provider === data.provider ? data : provider)),
        )
        toast.success('Credential saved', `${titleCase(editor.field)} is stored as a masked secret.`)
      } else {
        const { data } = await api.post(
          `/integrations/external/providers/${selectedProvider.provider}/credentials/${editor.field}/rotate`,
          { value: secretValue, window_hours: hours },
        )
        applyCredential(selectedProvider.provider, data)
        toast.success(
          'Rotation started',
          `The previous value remains valid until ${dateTimeLabel(data.rotation_ends_at)}.`,
        )
      }
      setEditor(null)
      setSecretValue('')
      setReason('')
    } catch (requestError) {
      setEditorError(apiErrorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  const mutateCredential = async (field, action) => {
    if (!selectedProvider) return
    setBusyField(`${field}:${action}`)
    try {
      const endpoint =
        action === 'commit'
          ? `/integrations/external/providers/${selectedProvider.provider}/credentials/${field}/commit`
          : `/integrations/external/providers/${selectedProvider.provider}/credentials/${field}/rollback`
      const { data } = await api.post(endpoint)
      applyCredential(selectedProvider.provider, data)
      if (action === 'commit') {
        toast.success('Rotation committed', `${titleCase(field)} is active on the new value.`)
      } else {
        toast.success('Rotation rolled back', `${titleCase(field)} is active on the previous value.`)
      }
    } catch (requestError) {
      toast.error(`Could not ${action} credential`, apiErrorMessage(requestError))
    } finally {
      setBusyField('')
    }
  }

  const runConnectionTest = async (provider) => {
    setTesting(provider.provider)
    try {
      const { data } = await api.post(
        `/integrations/external/providers/${provider.provider}/test-connection`,
      )
      const result = { ...data, checked_at: new Date().toISOString() }
      setTestResults((current) => ({ ...current, [provider.provider]: result }))
      if (data.status === 'degraded_simulated') {
        toast.error('Connection check degraded', data.detail)
      } else {
        toast.success('Connection check complete', data.detail)
      }
    } catch (requestError) {
      toast.error('Could not test connection', apiErrorMessage(requestError))
    } finally {
      setTesting('')
    }
  }

  if (!canRead) {
    return (
      <>
        <PageHeader
          eyebrow="Finance · Integrations"
          title="External integrations"
          description="Manage credentials for external tax, banking, payment and OCR providers."
        />
        <EmptyState
          icon={ShieldCheck}
          title="No integration access"
          description="Ask an administrator for integration channel or settings read access."
        />
      </>
    )
  }

  return (
    <>
      <PageHeader
        eyebrow="Finance · Integrations"
        title="External integrations"
        description="Store provider credentials as encrypted secrets, rotate them with a dual-control window, and verify connectivity."
        actions={
          <button type="button" className="btn-secondary" onClick={load} disabled={loading}>
            <RefreshCw size={15} /> Refresh
          </button>
        }
      />

      <div className="mb-5 flex items-start gap-3 rounded-2xl border border-primary/20 bg-primary-soft/50 p-4 text-sm text-ink-soft">
        <ShieldCheck className="mt-0.5 shrink-0 text-primary" size={18} />
        <p>
          Credentials are write-only. After saving, the API returns masks and key metadata only;
          secret values cannot be read back. Connection checks are simulated and never transmit
          credentials to the provider.
        </p>
      </div>

      {error && (
        <div className="card mb-5 flex items-start gap-3 p-5 text-sm text-rose-700">
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="card flex min-h-64 items-center justify-center gap-3 text-sm text-muted">
          <Spinner /> Loading external providers…
        </div>
      ) : (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.4fr)]">
          <SectionCard
            title="Providers"
            description={`${providers.length} external integrations available for this tenant.`}
          >
            <div className="divide-y divide-line">
              {providers.map((provider) => {
                const last = testResults[provider.provider]
                const active = provider.provider === selected
                return (
                  <button
                    key={provider.provider}
                    type="button"
                    onClick={() => setSelected(provider.provider)}
                    className={`block w-full px-5 py-4 text-left transition ${
                      active ? 'bg-primary-soft/60' : 'hover:bg-surface-2/60'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold text-ink">{provider.label}</p>
                        <p className="mt-1 text-xs text-muted">
                          {provider.provider} ·{' '}
                          {(provider.configured_fields ?? []).length}/
                          {(provider.required_fields ?? []).length} fields configured
                        </p>
                      </div>
                      <Badge>{provider.is_configured ? 'configured' : 'incomplete'}</Badge>
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                      <span>Last test:</span>
                      {last ? (
                        <>
                          <Badge>{last.status}</Badge>
                          <span>{dateTimeLabel(last.checked_at)}</span>
                        </>
                      ) : (
                        <span>not run yet</span>
                      )}
                    </div>
                  </button>
                )
              })}
              {!providers.length && (
                <p className="px-5 py-8 text-sm text-muted">No external providers are registered.</p>
              )}
            </div>
          </SectionCard>

          {selectedProvider && (
            <SectionCard
              title={`${selectedProvider.label} credentials`}
              description="Masks, key versions and rotation state are safe to review; values are never returned."
              action={
                canWrite && (
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => runConnectionTest(selectedProvider)}
                    disabled={Boolean(testing)}
                  >
                    {testing === selectedProvider.provider ? 'Testing…' : 'Test connection'}
                  </button>
                )
              }
            >
              <div className="divide-y divide-line">
                {(selectedProvider.credentials ?? []).map((credential) => (
                  <div key={credential.field} className="px-5 py-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold text-ink">{titleCase(credential.field)}</p>
                        <p className="mt-0.5 font-mono text-[11px] text-muted">{credential.key}</p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge>{credential.configured ? 'configured' : 'missing'}</Badge>
                        <Badge>{credential.status}</Badge>
                      </div>
                    </div>
                    <div className="mt-2 grid gap-1 text-xs text-muted">
                      <span>
                        Mask:{' '}
                        <span className="font-mono text-ink-soft">{credential.mask || '—'}</span>
                      </span>
                      <span>
                        Version {credential.key_version ?? 1} · {credential.algo} · Rotated{' '}
                        {dateTimeLabel(credential.rotated_at)} · Window ends{' '}
                        {dateTimeLabel(credential.rotation_ends_at)} · Last used{' '}
                        {dateTimeLabel(credential.last_used_at)}
                      </span>
                    </div>
                    {canWrite && (
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          className="btn-secondary py-1.5 text-xs"
                          onClick={() => openEditor('set', credential.field)}
                        >
                          Set value
                        </button>
                        <button
                          type="button"
                          className="btn-secondary py-1.5 text-xs"
                          onClick={() => openEditor('rotate', credential.field)}
                          disabled={!credential.configured}
                        >
                          Rotate
                        </button>
                        <button
                          type="button"
                          className="btn-secondary py-1.5 text-xs"
                          onClick={() => mutateCredential(credential.field, 'commit')}
                          disabled={credential.status !== 'pending' || Boolean(busyField)}
                        >
                          {busyField === `${credential.field}:commit` ? 'Committing…' : 'Commit'}
                        </button>
                        <button
                          type="button"
                          className="btn-secondary py-1.5 text-xs"
                          onClick={() => mutateCredential(credential.field, 'rollback')}
                          disabled={credential.status !== 'pending' || Boolean(busyField)}
                        >
                          {busyField === `${credential.field}:rollback` ? 'Rolling back…' : 'Rollback'}
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {testResults[selectedProvider.provider] && (
                <div className="border-t border-line bg-surface-2/50 px-5 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-xs font-bold uppercase tracking-wider text-muted">
                      Last test result
                    </p>
                    <Badge>{testResults[selectedProvider.provider].status}</Badge>
                    <span className="text-[11px] text-muted">
                      {dateTimeLabel(testResults[selectedProvider.provider].checked_at)}
                    </span>
                  </div>
                  <p className="mt-2 text-xs text-ink-soft">
                    {testResults[selectedProvider.provider].detail}
                  </p>
                  <p className="mt-1 text-[11px] text-muted">
                    Checked fields:{' '}
                    {(testResults[selectedProvider.provider].checked_fields ?? []).join(', ') || '—'}
                  </p>
                </div>
              )}
            </SectionCard>
          )}
        </div>
      )}

      <Modal
        open={Boolean(editor)}
        onClose={closeEditor}
        title={editor?.mode === 'rotate' ? 'Rotate credential' : 'Set credential'}
        description={
          editor
            ? `${selectedProvider?.label ?? ''} · ${titleCase(editor.field)}`
            : ''
        }
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={closeEditor} disabled={saving}>
              Cancel
            </button>
            <button
              type="submit"
              form="external-credential-form"
              className="btn-primary"
              disabled={saving || !secretValue.trim()}
            >
              {saving ? 'Saving…' : editor?.mode === 'rotate' ? 'Start rotation' : 'Save credential'}
            </button>
          </>
        }
      >
        <form id="external-credential-form" onSubmit={saveCredential} className="grid gap-4">
          <label className="form-label">
            {editor?.mode === 'rotate' ? 'Replacement value' : 'Secret value'}
            <input
              className="input mt-1.5"
              type="password"
              autoComplete="new-password"
              required
              value={secretValue}
              onChange={(event) => setSecretValue(event.target.value)}
            />
          </label>
          {editor?.mode === 'rotate' ? (
            <label className="form-label">
              Overlap window (hours)
              <input
                className="input mt-1.5"
                type="number"
                min={1}
                max={720}
                value={windowHours}
                onChange={(event) => setWindowHours(event.target.value)}
              />
            </label>
          ) : (
            <label className="form-label">
              Audit reason (optional)
              <input
                className="input mt-1.5"
                maxLength={500}
                value={reason}
                placeholder="Initial setup"
                onChange={(event) => setReason(event.target.value)}
              />
            </label>
          )}
          {editorError && <p className="text-xs font-semibold text-rose-600">{editorError}</p>}
        </form>
      </Modal>
    </>
  )
}
