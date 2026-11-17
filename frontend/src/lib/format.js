import clsx from 'clsx'

export { clsx as cn }

const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

const inrPrecise = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export const money = (value, { precise = false } = {}) => {
  const number = Number(value ?? 0)
  if (Number.isNaN(number)) return precise ? inrPrecise.format(0) : inr.format(0)
  return (precise ? inrPrecise : inr).format(number)
}

export const compactMoney = (value) => {
  const number = Number(value ?? 0)
  if (Math.abs(number) >= 10000000) return `₹${(number / 10000000).toFixed(2)} Cr`
  if (Math.abs(number) >= 100000) return `₹${(number / 100000).toFixed(2)} L`
  if (Math.abs(number) >= 1000) return `₹${(number / 1000).toFixed(1)}k`
  return inr.format(number)
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
  positive: ['paid', 'active', 'confirmed', 'fulfilled', 'approved', 'won', 'delivered', 'processed', 'resolved', 'completed', 'done', 'present', 'received', 'posted'],
  warning: ['pending', 'pending_approval', 'draft', 'scheduled', 'partially_received', 'on_hold', 'qualification', 'negotiation', 'sent', 'open', 'in_progress', 'todo'],
  danger: ['overdue', 'cancelled', 'failed', 'rejected', 'closed', 'lost', 'absent', 'inactive', 'dispatched'],
  info: ['new', 'new_lead', 'contacted', 'proposal', 'manual', 'web', 'bank', 'cash', 'whatsapp', 'pos', 'inventory', 'sale', 'receipt', 'adjustment'],
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
