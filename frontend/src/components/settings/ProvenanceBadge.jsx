import { cn, statusTone, statusClasses } from '../../lib/format'

export function provenanceParts(setting) {
  const raw = String(setting?.effective_source ?? 'default')
  const source = raw.startsWith('inherits') ? 'inherited' : raw.split(':')[0]
  const scope = setting?.scope_type ?? (source === 'tenant' || source === 'default' || source === 'env' ? source : source)
  const scopeId = setting?.scope_id ?? (raw.includes(':') ? raw.slice(raw.indexOf(':') + 1) : null)
  return { raw, source, scope, scopeId, version: Number(setting?.stored_version ?? 0) }
}

export default function ProvenanceBadge({ setting, compact = false }) {
  const { raw, source, scope, scopeId, version } = provenanceParts(setting)
  const detail = `${raw} · scope ${scope}${scopeId ? `:${scopeId}` : ''} · stored version ${version}`
  return (
    <span
      className={cn('inline-flex max-w-full flex-wrap items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset', statusClasses[statusTone(source)])}
      data-testid={`provenance-${setting?.key ?? 'unknown'}`}
      data-source={source}
      data-scope={scope}
      data-version={version}
      title={detail}
    >
      <span className="truncate">{compact ? source : `Source: ${source} · v${version}`}</span>
      {!compact && <span className="hidden opacity-70 sm:inline">· {scope}</span>}
    </span>
  )
}
