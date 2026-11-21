import { useEffect, useMemo, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, BadgeIndianRupee, Banknote, BookOpen, CircleDollarSign, FileText, Landmark, Receipt, Scale } from 'lucide-react'
import { Link } from 'react-router-dom'
import { EmptyState, KpiCard, PageHeader, SectionCard, Spinner } from '../components/ui'
import { api, apiErrorMessage } from '../lib/api'
import { money } from '../lib/format'
import { describePath } from '../lib/nav'
import { useAuth } from '../store/auth'

const WORKFLOWS = [
  { title: 'Customer invoices', detail: 'Create invoices, post receivables, and follow collections.', to: '/finance/invoices', icon: FileText },
  { title: 'Vendor payments', detail: 'Review approved bills and settle payables against the ledger.', to: '/finance/vendor-payments', icon: Receipt },
  { title: 'Bank reconciliation', detail: 'Import statements, match posted ledger lines, and review exceptions.', to: '/finance/bank-reconciliation', icon: Landmark },
  { title: 'GST configuration', detail: 'Maintain registrations, tax codes, component rates, and ledger mappings.', to: '/finance/gst', icon: BadgeIndianRupee },
  { title: 'Journal entries', detail: 'Post adjustments and review immutable ledger activity.', to: '/finance/journal-entries', icon: BookOpen },
  { title: 'Bank accounts', detail: 'Maintain settlement accounts and their general-ledger mappings.', to: '/finance/bank-accounts', icon: Landmark },
]

export default function FinanceDashboard() {
  const canView = useAuth().canView
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    Promise.all([
      api.get('/finance/reports/profit-loss'),
      api.get('/finance/reports/balance-sheet'),
      api.get('/finance/reports/receivables'),
      api.get('/finance/reports/cash-flow'),
      api.get('/finance/reports/trial-balance'),
      api.get('/finance/reports/grni'),
    ])
      .then(([profitLoss, balanceSheet, receivables, cashFlow, trialBalance, grni]) => {
        if (active) setData({
          profitLoss: profitLoss.data,
          balanceSheet: balanceSheet.data,
          receivables: receivables.data,
          cashFlow: cashFlow.data,
          trialBalance: trialBalance.data,
          grni: grni.data,
        })
      })
      .catch((requestError) => {
        if (active) setError(apiErrorMessage(requestError, 'Could not load the finance overview.'))
      })
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  const totals = useMemo(() => {
    if (!data) return null
    const outstanding = data.receivables.reduce((sum, item) => sum + Number(item.outstanding ?? 0), 0)
    const overdue = data.receivables
      .filter((item) => Number(item.days_overdue ?? 0) > 0)
      .reduce((sum, item) => sum + Number(item.outstanding ?? 0), 0)
    const trialDebits = data.trialBalance.reduce((sum, item) => sum + Number(item.debit ?? 0), 0)
    const trialCredits = data.trialBalance.reduce((sum, item) => sum + Number(item.credit ?? 0), 0)
    return {
      outstanding,
      overdue,
      cash: data.cashFlow.total,
      grni: data.grni.outstanding_total,
      netProfit: data.profitLoss.total,
      balanced: Math.abs(trialDebits - trialCredits) < 0.01,
    }
  }, [data])

  if (loading) {
    return <div className="flex min-h-64 items-center justify-center gap-3 text-sm text-muted"><Spinner /> Loading finance overview…</div>
  }
  if (error) {
    return <EmptyState title="Finance overview unavailable" description={error} action={<button className="btn-primary" type="button" onClick={() => window.location.reload()}>Try again</button>} />
  }

  return (
    <>
      <PageHeader
        eyebrow="Accounting workspace"
        title="Finance overview"
        description="A working view of ledger health, cash movement, receivables, and the accounting workflows that need attention."
        actions={<Link className="btn-primary" to="/finance/reports"><Scale size={15} /> Open financial statements</Link>}
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5 stagger">
        <KpiCard label="Net profit" value={money(totals.netProfit)} hint="Posted income less expenses" icon={CircleDollarSign} tone="primary" />
        <KpiCard label="Receivables" value={money(totals.outstanding)} hint="Open customer balances" icon={ArrowUpRight} tone="accent" />
        <KpiCard label="Overdue" value={money(totals.overdue)} hint="Past their due date" icon={ArrowDownRight} tone="gold" />
        <KpiCard label="Cash inflow" value={money(totals.cash)} hint="Recorded customer receipts" icon={Banknote} tone="sky" />
        <KpiCard label="Open GRNI" value={money(totals.grni)} hint={`${data.grni.receipt_count} uncleared receipts`} icon={Receipt} tone="gold" />
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.4fr_0.8fr]">
        <SectionCard title="Accounting workbench" description="Go directly to the operational task, not just the underlying records.">
          <div className="grid gap-3 p-4 sm:grid-cols-2">
            {WORKFLOWS.filter((item) => canView(describePath(item.to))).map(({ title, detail, to, icon: Icon }) => (
              <Link key={to} to={to} className="group rounded-2xl border border-line bg-surface p-4 transition hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-[var(--shadow-float)]">
                <span className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary-soft text-primary"><Icon size={18} /></span>
                <h2 className="text-sm font-bold text-ink group-hover:text-primary">{title}</h2>
                <p className="mt-1.5 text-xs leading-relaxed text-muted">{detail}</p>
              </Link>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Ledger health" description="Based on posted journals only.">
          <div className="space-y-3 p-5">
            <div className="flex items-center justify-between rounded-xl bg-surface-2/70 p-3.5">
              <div>
                <p className="text-xs font-semibold text-ink">Trial balance</p>
                <p className="mt-0.5 text-[11px] text-muted">Total debit and credit balances</p>
              </div>
              <span className={`badge ${totals.balanced ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-rose-50 text-rose-700 ring-rose-200'}`}>
                {totals.balanced ? 'Balanced' : 'Review'}
              </span>
            </div>
            {(data.balanceSheet.sections ?? []).map((section) => (
              <div key={section.label} className="flex items-center justify-between border-b border-line/70 py-2 last:border-0">
                <span className="text-xs text-muted">{section.label}</span>
                <span className="text-sm font-semibold tabular-nums text-ink">{money(section.amount)}</span>
              </div>
            ))}
            <p className="rounded-xl border border-line bg-surface-2/40 p-3 text-[11px] leading-relaxed text-muted">
              Financial statements reflect posted journals. Draft journals and unapproved source documents are excluded.
            </p>
          </div>
        </SectionCard>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <SectionCard title="Collections requiring attention" description="Largest open customer balances first." action={<Link className="text-xs font-bold text-primary hover:underline" to="/finance/reports">View receivables</Link>}>
          <div className="divide-y divide-line">
            {data.receivables.slice(0, 5).map((invoice) => (
              <div key={invoice.invoice_id} className="flex items-center justify-between gap-4 px-5 py-3.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink">{invoice.invoice_number}</p>
                  <p className="mt-0.5 text-[11px] text-muted">{invoice.days_overdue > 0 ? `${invoice.days_overdue} days overdue` : 'Not overdue'}</p>
                </div>
                <p className="shrink-0 text-sm font-bold tabular-nums text-ink">{money(invoice.outstanding)}</p>
              </div>
            ))}
            {!data.receivables.length && <EmptyState compact title="No open receivables" description="Posted customer invoices will appear here." />}
          </div>
        </SectionCard>

        <SectionCard title="Cash movement" description="Customer inflows grouped by payment method." action={<Link className="text-xs font-bold text-primary hover:underline" to="/finance/payments">Payment register</Link>}>
          <div className="divide-y divide-line">
            {(data.cashFlow.sections ?? []).slice(0, 5).map((section) => (
              <div key={section.label} className="flex items-center justify-between px-5 py-3.5">
                <span className="text-sm capitalize text-ink-soft">{section.label}</span>
                <span className="text-sm font-semibold tabular-nums text-ink">{money(section.amount)}</span>
              </div>
            ))}
            {!data.cashFlow.sections?.length && <EmptyState compact title="No cash activity" description="Posted receipts will be summarized here." />}
          </div>
        </SectionCard>
      </div>
      <p className="mt-6 text-center text-[10px] text-muted">Overview generated {new Date().toLocaleString('en-IN')}</p>
    </>
  )
}
