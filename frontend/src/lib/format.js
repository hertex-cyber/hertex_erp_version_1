import clsx from 'clsx'

export { clsx as cn }

const formatterCache = new Map()

export function isRestrictedValue(value) {
  if (value === null || value === undefined) return true
  if (typeof value !== 'string') return false
  return ['', 'restricted', 'masked', 'null'].includes(value.trim().toLowerCase())
}

export function resolveCurrency(value, fallback = 'INR') {
  const candidate = typeof value === 'string' ? value.trim().toUpperCase() : ''
  return /^[A-Z]{3}$/.test(candidate) ? candidate : fallback
}

function currencyFormatter(currency, precise) {
  const resolved = resolveCurrency(currency)
  const key = `${resolved}:${precise ? 'p' : 'i'}`
  if (!formatterCache.has(key)) {
    formatterCache.set(
      key,
      new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: resolved,
        ...(precise
          ? { minimumFractionDigits: 2, maximumFractionDigits: 2 }
          : { maximumFractionDigits: 0 }),
      }),
    )
  }
  return formatterCache.get(key)
}

export const money = (value, { precise = false, currency = 'INR', restricted = false } = {}) => {
  if (restricted && isRestrictedValue(value)) return 'Restricted'
  const number = Number(value ?? 0)
  const formatter = currencyFormatter(currency, precise)
  if (Number.isNaN(number)) return formatter.format(0)
  return formatter.format(number)
}

export const compactMoney = (value, { currency = 'INR', restricted = false } = {}) => {
  if (restricted && isRestrictedValue(value)) return 'Restricted'
  const number = Number(value ?? 0)
  const resolved = resolveCurrency(currency)
  const symbol =
    resolved === 'INR'
      ? '₹'
      : new Intl.NumberFormat('en-IN', { style: 'currency', currency: resolved })
          .formatToParts(0)
          .find((part) => part.type === 'currency')?.value ?? resolved
  if (Number.isNaN(number)) return `${symbol}0`
  if (Math.abs(number) >= 10000000) return `${symbol}${(number / 10000000).toFixed(2)} Cr`
  if (Math.abs(number) >= 100000) return `${symbol}${(number / 100000).toFixed(2)} L`
  if (Math.abs(number) >= 1000) return `${symbol}${(number / 1000).toFixed(1)}k`
  return currencyFormatter(resolved, false).format(number)
}

export const num = (value, digits = 0) => {
  const number = Number(value ?? 0)
  if (Number.isNaN(number)) return '0'
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: digits }).format(number)
}

export const pct = (value, digits = 0) => `${num(Number(value ?? 0), digits)}%`

export const dateLabel = (value, options = {}) => {
  if (!value) return '—'
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', ...options })
}

export const dateTimeLabel = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export const timeLabel = (value) => {
  if (!value) return '—'
  const [h, m] = String(value).split(':')
  const date = new Date()
  date.setHours(Number(h), Number(m), 0, 0)
  return date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
}

export const today = () => new Date().toISOString().slice(0, 10)

export const titleCase = (value) =>
  String(value ?? '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())

export const initials = (name) =>
  String(name ?? '')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'H'

const tones = {
  positive: ['paid', 'active', 'activated', 'confirmed', 'fulfilled', 'approved', 'won', 'delivered', 'processed', 'resolved', 'completed', 'done', 'present', 'received', 'posted', 'accepted', 'reached', 'billed', 'invoiced', 'published', 'applied', 'executed', 'committed', 'validated', 'succeeded', 'success', 'green', 'approved_changes'],
  warning: ['pending', 'pending_approval', 'approval_pending', 'draft', 'scheduled', 'partially_received', 'on_hold', 'hold', 'qualification', 'negotiation', 'sent', 'open', 'in_progress', 'todo', 'in_review', 'review', 'submitted', 'identified', 'analysing', 'planned', 'proposed', 'requested', 'staged', 'validating', 'triaged', 'advisory', 'amber'],
  danger: ['overdue', 'cancelled', 'failed', 'rejected', 'closed', 'lost', 'absent', 'inactive', 'dispatched', 'blocked', 'escalated', 'rolled_back', 'rollback', 'red'],
  info: ['new', 'new_lead', 'contacted', 'proposal', 'manual', 'web', 'bank', 'cash', 'whatsapp', 'pos', 'inventory', 'sale', 'receipt', 'adjustment', 'backlog', 'mitigated', 'running', 'unknown', 'baseline', 'critical', 'dependency'],
}

export function statusTone(status) {
  const key = String(status ?? '').toLowerCase()
  for (const [tone, values] of Object.entries(tones)) {
    if (values.includes(key)) return tone
  }
  return 'neutral'
}

export const statusClasses = {
  positive: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  warning: 'bg-amber-50 text-amber-700 ring-amber-200',
  danger: 'bg-rose-50 text-rose-700 ring-rose-200',
  info: 'bg-sky-50 text-sky-700 ring-sky-200',
  neutral: 'bg-stone-100 text-stone-600 ring-stone-200',
}

export function debounce(fn, wait = 300) {
  let timer
  return (...args) => {
    clearTimeout(timer)
    timer = setTimeout(() => fn(...args), wait)
  }
}
