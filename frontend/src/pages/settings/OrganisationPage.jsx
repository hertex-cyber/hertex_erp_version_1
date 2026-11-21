import { Check, Circle } from 'lucide-react'
import { PageHeader, LoadingBlock } from '../../components/ui'
import SettingsSubnav from '../../components/settings/SettingsSubnav'
import SettingSection from '../../components/settings/SettingSection'
import useSettingValues from '../../components/settings/useSettingValues'

const REQUIRED = [
  { key: 'company.profile.name', label: 'Registered business name' },
  { key: 'company.profile.gstin', label: 'GSTIN' },
  { key: 'company.profile.state_code', label: 'GST state code' },
  { key: 'company.profile.legal_name', label: 'Legal name' },
]

export default function OrganisationPage() {
  const { rows, loading, error, reload } = useSettingValues({ module: 'company' })
  const byKey = Object.fromEntries(rows.map((row) => [row.key, row]))
  const done = REQUIRED.filter((item) => Boolean(byKey[item.key]?.value)).length

  return (
    <div data-testid="organisation-page">
      <SettingsSubnav />
      <PageHeader eyebrow="Settings" title="Organisation" description="Statutory company particulars that appear on invoices and drive GST treatment." />
      {loading && <LoadingBlock label="Loading organisation settings…" />}
      {error && <p className="card p-4 text-sm text-rose-600">{error}</p>}
      <div className="card mb-5 p-4 sm:p-5" data-testid="profile-checklist">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-bold text-ink">Complete your profile</h2>
          <span className="text-xs font-bold text-primary">{done}/{REQUIRED.length} complete</span>
        </div>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {REQUIRED.map((item) => {
            const complete = Boolean(byKey[item.key]?.value)
            return (
              <li key={item.key} className="flex items-center gap-2 text-xs text-ink-soft">
                {complete ? <Check size={15} className="text-emerald-600" /> : <Circle size={15} className="text-muted" />}
                {item.label}
              </li>
            )
          })}
        </ul>
      </div>
      {!loading && (
        <SettingSection
          title="Company profile"
          description="Critical fields require a reason and are visible in the change history."
          note="Changing the GST state code or legal name affects future documents. Existing invoices retain their original particulars."
          rows={rows}
          onSaved={reload}
        />
      )}
    </div>
  )
}
