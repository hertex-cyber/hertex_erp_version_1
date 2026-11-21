import { PageHeader, LoadingBlock } from '../../components/ui'
import SettingsSubnav from '../../components/settings/SettingsSubnav'
import SettingSection from '../../components/settings/SettingSection'
import useSettingValues from '../../components/settings/useSettingValues'
import { dateLabel, money, resolveCurrency } from '../../lib/format'

export default function LocalisationPage() {
  const { rows, loading, error, reload } = useSettingValues({ module: 'localization' })
  const byKey = Object.fromEntries(rows.map((row) => [row.key, row]))
  const currency = resolveCurrency(byKey['company.locale.currency']?.value, 'INR')
  const startMonth = Number(byKey['company.fiscal.start_month']?.value ?? 4)
  const fiscalLabel = startMonth === 4 ? 'April – March' : startMonth === 1 ? 'January – December' : `Month ${startMonth} start`
  const sampleDate = '2026-04-01'

  return (
    <div data-testid="localisation-page">
      <SettingsSubnav />
      <PageHeader eyebrow="Settings" title="Localisation" description="Currency, time and fiscal calendar defaults used across documents and reports." />
      {loading && <LoadingBlock label="Loading localisation settings…" />}
      {error && <p className="card p-4 text-sm text-rose-600">{error}</p>}
      <div className="card mb-5 p-4 sm:p-5" data-testid="localisation-preview">
        <h2 className="text-sm font-bold text-ink">Live format preview</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl bg-surface-2 p-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-muted">Amount</p>
            <p className="mt-1 font-mono text-lg font-bold text-ink">{money(123456.78, { currency, precise: true })}</p>
          </div>
          <div className="rounded-xl bg-surface-2 p-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-muted">Date</p>
            <p className="mt-1 font-mono text-lg font-bold text-ink">{dateLabel(sampleDate)}</p>
          </div>
          <div className="rounded-xl bg-surface-2 p-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-muted">Fiscal year</p>
            <p className="mt-1 font-mono text-lg font-bold text-ink">{fiscalLabel}</p>
          </div>
        </div>
      </div>
      {!loading && (
        <SettingSection
          title="Locale and fiscal calendar"
          description="Base currency and fiscal-year start are critical and lock after the first posting."
          note="Formats change how values are displayed; they never change stored ledger amounts."
          rows={rows}
          onSaved={reload}
        />
      )}
    </div>
  )
}
