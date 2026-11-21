import { useMemo, useState } from 'react'
import { PageHeader, LoadingBlock } from '../../components/ui'
import SettingsSubnav from '../../components/settings/SettingsSubnav'
import SettingSection from '../../components/settings/SettingSection'
import useSettingValues from '../../components/settings/useSettingValues'

export default function ValuesPage() {
  const { rows, loading, error, reload } = useSettingValues()
  const [query, setQuery] = useState('')
  const [module, setModule] = useState('all')

  const modules = useMemo(() => ['all', ...Array.from(new Set(rows.map((row) => row.module))).sort()], [rows])
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return rows.filter((row) => {
      if (module !== 'all' && row.module !== module) return false
      if (!needle) return true
      return `${row.key} ${row.label} ${row.help}`.toLowerCase().includes(needle)
    })
  }, [rows, module, query])

  return (
    <div data-testid="settings-values-page">
      <SettingsSubnav />
      <PageHeader
        eyebrow="Settings"
        title="All settings"
        description="Typed, governed configuration values with provenance, mandatory reasons on critical keys and full change history."
      />
      <div className="mb-5 grid gap-2 sm:grid-cols-2">
        <input className="input w-full" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search settings" data-testid="settings-search" />
        <select className="input w-full" value={module} onChange={(event) => setModule(event.target.value)} data-testid="settings-module-filter">
          {modules.map((name) => <option key={name} value={name}>{name === 'all' ? 'All modules' : name}</option>)}
        </select>
      </div>
      {loading && <LoadingBlock label="Loading settings…" />}
      {error && <p className="card p-4 text-sm text-rose-600">{error}</p>}
      {!loading && (
        <SettingSection
          title={`${visible.length} registered setting${visible.length === 1 ? '' : 's'}`}
          description="Values shown are effective for this tenant. Source badges explain defaults, deployment configuration and scope overrides."
          note="Every change is recorded with actor, time, before/after and reason. Critical keys are staged for approval when required."
          rows={visible}
          onSaved={reload}
          empty="No settings match this filter."
        />
      )}
    </div>
  )
}
