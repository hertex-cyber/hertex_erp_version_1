import { useEffect, useState } from 'react'
import { fetchLookup } from '../lib/lookups'
import { dateLabel, money, num, statusTone, titleCase } from '../lib/format'
import { Badge } from './ui'

const optionCache = new Map()
const promiseCache = new Map()

export function loadLookupCached(key) {
  if (optionCache.has(key)) return Promise.resolve(optionCache.get(key))
  if (promiseCache.has(key)) return promiseCache.get(key)
  const promise = fetchLookup(key)
    .then((options) => {
      optionCache.set(key, options)
      promiseCache.delete(key)
      return options
    })
    .catch((error) => {
      promiseCache.delete(key)
      throw error
    })
  promiseCache.set(key, promise)
  return promise
}

export function Ref({ lookup, id, fallback = '—' }) {
  const [label, setLabel] = useState(() =>
    optionCache.has(lookup) ? optionCache.get(lookup).find((option) => option.value === id)?.label : null,
  )

  useEffect(() => {
    if (!id) return undefined
    let active = true
    loadLookupCached(lookup)
      .then((options) => {
        if (!active) return
        setLabel(options.find((option) => option.value === id)?.label ?? null)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [lookup, id])

  if (!id) return <span className="text-muted">{fallback}</span>
  if (!label) {
    return (
      <span className="inline-flex items-center gap-1.5 text-muted">
        <span className="h-3 w-3 animate-pulse rounded-full bg-line" />
        <span className="text-[11px]">{String(id).slice(0, 8)}…</span>
      </span>
    )
  }
  return <span className="text-ink-soft">{label}</span>
}

export function Money({ value, precise = false, className = '' }) {
  return <span className={`font-semibold tabular-nums text-ink ${className}`}>{money(value, { precise })}</span>
}

export function Qty({ value, className = '' }) {
  return <span className={`font-semibold tabular-nums ${className}`}>{num(value, 2)}</span>
}

export function DateCell({ value, time = false }) {
  return <span className="text-ink-soft">{time ? new Date(value).toLocaleString('en-IN') : dateLabel(value)}</span>
}

export function Status({ value }) {
  return <Badge tone={statusTone(value)}>{value}</Badge>
}

export function Primary({ title, subtitle, badge }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="min-w-0">
        <p className="truncate font-semibold text-ink">{title || '—'}</p>
        {subtitle && <p className="mt-0.5 truncate text-[11px] text-muted">{subtitle}</p>}
      </div>
      {badge}
    </div>
  )
}

export function TypeBadge({ value }) {
  return <Badge tone={statusTone(value)}>{titleCase(value)}</Badge>
}
