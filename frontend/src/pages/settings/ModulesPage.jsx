import { useEffect, useState } from 'react'
import { PageHeader, LoadingBlock } from '../../components/ui'
import SettingsSubnav from '../../components/settings/SettingsSubnav'
import SettingSection from '../../components/settings/SettingSection'
import useSettingValues from '../../components/settings/useSettingValues'
import { api } from '../../lib/api'

export default function ModulesPage() {
  const { rows, loading, error, reload } = useSettingValues({ module: 'features' })
  const [flags, setFlags] = useState({})

  useEffect(() => {
    api.get('/settings/features').then((response) => setFlags(response.data ?? {})).catch(() => setFlags({}))
  }, [rows])

  const modules = rows.filter((row) => row.key.startsWith('features.module.'))
  const beta = rows.filter((row) => row.key.startsWith('features.beta.'))
  const other = rows.filter((row) => !modules.includes(row) && !beta.includes(row))
  const enabled = Object.values(flags).filter(Boolean).length

  return (
    <div data-testid="modules-page">
      <SettingsSubnav />
      <PageHeader eyebrow="Settings" title="Modules & features" description="Enable modules and stage beta features for this workspace." />
      <p className="card mb-5 border-sky-200 bg-sky-50 p-4 text-xs leading-relaxed text-sky-700" data-testid="api-stays-live-note">
        <strong>API stays live when a module is disabled.</strong> Toggles change navigation and UI workflows only; existing API endpoints and stored data remain available for integrations and migrations.
      </p>
      {loading && <LoadingBlock label="Loading feature flags…" />}
      {error && <p className="card p-4 text-sm text-rose-600">{error}</p>}
      {!loading && (
        <div className="space-y-7">
          <p className="text-xs text-muted" data-testid="resolved-feature-count">{enabled} of {Object.keys(flags).length} resolved flags enabled</p>
          <SettingSection title="Enabled modules" description="Module switches are audited critical settings." rows={modules} onSaved={reload} />
          <SettingSection title="Beta features" description="Staged rollout switches for new capabilities." rows={beta} onSaved={reload} />
          <SettingSection title="Other feature flags" rows={other} onSaved={reload} />
        </div>
      )}
    </div>
  )
}
