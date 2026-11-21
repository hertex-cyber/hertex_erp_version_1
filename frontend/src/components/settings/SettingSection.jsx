import SettingField from './SettingField'

export default function SettingSection({ title, description, note, rows = [], onSaved, empty = 'No settings are registered in this group.' }) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-base font-bold text-ink">{title}</h2>
        {description && <p className="mt-1 text-xs text-muted">{description}</p>}
      </div>
      {note && <p className="rounded-xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-700">{note}</p>}
      <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
        {rows.map((row) => <SettingField key={row.key} setting={row} onSaved={onSaved} />)}
      </div>
      {!rows.length && <p className="card p-5 text-sm text-muted">{empty}</p>}
    </section>
  )
}
