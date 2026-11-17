import { useEffect } from 'react'
import { CheckCircle2, ChevronLeft, ChevronRight, Info, Search, TriangleAlert, X } from 'lucide-react'
import { cn, initials, num, statusClasses, statusTone, titleCase } from '../lib/format'
import { useToast } from '../store/toast'

export function Spinner({ className = 'h-5 w-5' }) {
  return (
    <span
      className={cn('inline-block animate-spin rounded-full border-2 border-current border-t-transparent', className)}
      role="status"
      aria-label="Loading"
    />
  )
}

export function LoadingBlock({ label = 'Loading workspace…' }) {
  return (
    <div className="card flex flex-col items-center justify-center gap-3 px-6 py-20 text-muted">
      <Spinner className="h-6 w-6 text-primary" />
      <p className="text-sm font-medium">{label}</p>
    </div>
  )
}

export function Badge({ children, tone, className }) {
  return (
    <span className={cn('badge', statusClasses[tone ?? statusTone(children)], className)}>
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {titleCase(children)}
    </span>
  )
}

export function Avatar({ name, size = 'md', className }) {
  const sizes = { sm: 'h-8 w-8 text-[10px]', md: 'h-10 w-10 text-xs', lg: 'h-12 w-12 text-sm' }
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full bg-primary-soft font-bold text-primary ring-1 ring-primary/10',
        sizes[size],
        className,
      )}
    >
      {initials(name)}
    </span>
  )
}

export function PageHeader({ eyebrow, title, description, actions, children }) {
  return (
    <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
        <h1 className="display text-3xl font-semibold text-ink sm:text-[2.1rem]">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function KpiCard({ label, value, delta, hint, icon: Icon, tone = 'primary', spark }) {
  const tones = {
    primary: 'bg-primary-soft text-primary',
    accent: 'bg-accent-soft text-accent',
    gold: 'bg-gold-soft text-gold',
    sky: 'bg-sky-50 text-sky-700',
  }
  const positive = Number(delta) >= 0
  return (
    <div className="card group relative overflow-hidden p-5 transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-float)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">{label}</p>
          <p className="display mt-2 text-[1.7rem] font-semibold leading-none text-ink">{value}</p>
        </div>
        {Icon && (
          <span className={cn('inline-flex h-10 w-10 items-center justify-center rounded-xl', tones[tone])}>
            <Icon size={18} strokeWidth={2} />
          </span>
        )}
      </div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs">
          {delta !== undefined && delta !== null && (
            <span
              className={cn(
                'inline-flex items-center rounded-full px-2 py-0.5 font-bold',
                positive ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700',
              )}
            >
              {positive ? '+' : ''}{num(delta, 1)}%
            </span>
          )}
          {hint && <span className="truncate text-muted">{hint}</span>}
        </div>
        {spark?.length > 1 && <Sparkline values={spark} />}
      </div>
    </div>
  )
}

function Sparkline({ values }) {
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const range = max - min || 1
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * 64
      const y = 22 - ((value - min) / range) * 20
      return `${x},${y}`
    })
    .join(' ')
  return (
    <svg viewBox="0 0 64 24" className="h-6 w-16 text-primary/60" aria-hidden="true">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function Pagination({ page, pages, total, size, onPage }) {
  if (!total) return null
  const from = (page - 1) * size + 1
  const to = Math.min(page * size, total)
  return (
    <div className="flex flex-col items-center justify-between gap-3 border-t border-line px-5 py-3.5 text-xs text-muted sm:flex-row">
      <p>
        Showing <span className="font-semibold text-ink">{from}–{to}</span> of{' '}
        <span className="font-semibold text-ink">{num(total)}</span>
      </p>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-line bg-surface text-ink-soft transition hover:bg-surface-2 disabled:opacity-40"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft size={15} />
        </button>
        <span className="px-2 font-semibold text-ink">
          {page} / {Math.max(pages, 1)}
        </span>
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-line bg-surface text-ink-soft transition hover:bg-surface-2 disabled:opacity-40"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight size={15} />
        </button>
      </div>
    </div>
  )
}

export function SearchInput({ value, onChange, placeholder = 'Search…', className }) {
  return (
    <div className={cn('relative', className)}>
      <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
      <input
        className="input pl-10"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
    </div>
  )
}

export function EmptyState({ icon: Icon, title, description, action, compact = false }) {
  return (
    <div className={cn('flex flex-col items-center justify-center px-6 text-center', compact ? 'py-10' : 'py-20')}>
      {Icon && (
        <span className="mb-4 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-2 text-muted ring-1 ring-line">
          <Icon size={24} strokeWidth={1.7} />
        </span>
      )}
      <h3 className="display text-lg font-semibold text-ink">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function Modal({ open, onClose, title, description, children, footer, size = 'md' }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (event) => {
      if (event.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null
  const sizes = { sm: 'max-w-md', md: 'max-w-2xl', lg: 'max-w-4xl', xl: 'max-w-6xl' }
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-forest/50 p-0 backdrop-blur-sm sm:items-center sm:p-6">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="Close dialog" onClick={onClose} />
      <div
        className={cn(
          'animate-in relative flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-3xl border border-line bg-surface shadow-[var(--shadow-float)] sm:rounded-3xl',
          sizes[size],
        )}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
          <div>
            <h2 className="display text-xl font-semibold text-ink">{title}</h2>
            {description && <p className="mt-1 text-sm text-muted">{description}</p>}
          </div>
          <button type="button" className="btn-ghost -mr-2 h-9 w-9 rounded-full px-0" onClick={onClose} aria-label="Close">
            <X size={17} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-line bg-surface-2 px-6 py-4">{footer}</div>}
      </div>
    </div>
  )
}

export function ToastHost() {
  const { toasts, dismiss } = useToast()
  const icons = { success: CheckCircle2, error: TriangleAlert, info: Info }
  const tones = {
    success: 'text-emerald-600',
    error: 'text-rose-600',
    info: 'text-sky-600',
  }
  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[60] flex w-[calc(100%-2rem)] max-w-sm flex-col gap-2.5">
      {toasts.map((item) => {
        const Icon = icons[item.tone] ?? Info
        return (
          <div
            key={item.id}
            className="animate-in pointer-events-auto flex items-start gap-3 rounded-2xl border border-line bg-surface p-4 shadow-[var(--shadow-float)]"
          >
            <Icon size={20} className={cn('mt-0.5 shrink-0', tones[item.tone])} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-bold text-ink">{item.title}</p>
              {item.description && <p className="mt-0.5 text-xs leading-relaxed text-muted">{item.description}</p>}
            </div>
            <button type="button" className="text-muted hover:text-ink" onClick={() => dismiss(item.id)} aria-label="Dismiss">
              <X size={15} />
            </button>
          </div>
        )
      })}
    </div>
  )
}

export function SectionCard({ title, description, action, children, className, bodyClassName }) {
  return (
    <section className={cn('card overflow-hidden', className)}>
      {(title || action) && (
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            {title && <h2 className="text-sm font-bold text-ink">{title}</h2>}
            {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
          </div>
          {action}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  )
}
