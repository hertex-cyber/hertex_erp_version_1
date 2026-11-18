import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowDownRight, ArrowUpRight, Banknote, BookOpen, CircleDollarSign, Download, FileText, Printer, Scale } from 'lucide-react'
import { api, apiErrorMessage } from '../lib/api'
import { cn, money, num, titleCase } from '../lib/format'
import { EmptyState, KpiCard, PageHeader, SectionCard, Spinner } from '../components/ui'

const TABS = [
  { key: 'profit-loss', label: 'Profit & loss' },
  { key: 'balance-sheet', label: 'Balance sheet' },
  { key: 'trial-balance', label: 'Trial balance' },
  { key: 'receivables', label: 'Receivables' },
  { key: 'aging', label: 'Aging' },
  { key: 'exceptions', label: 'Exceptions' },
  { key: 'cash-flow', label: 'Cash flow' },
]

function StatementCard({ title, report, tone = 'primary' }) {
  if (!report) return null
  return (
    <SectionCard title={title} description="Derived from posted journal entries.">
      <div className="divide-y divide-line">
        {(report.sections ?? []).map((section) => (
          <div key={section.label} className="flex items-center justify-between px-5 py-4">
            <span className="text-sm text-ink-soft">{section.label}</span>
            <span className="font-semibold tabular-nums text-ink">{money(section.amount)}</span>
          </div>
        ))}
      </div>
      <div className={cn('flex items-center justify-between px-5 py-4', tone === 'primary' ? 'bg-primary-soft/50' : 'bg-gold-soft/40')}>
        <span className="text-xs font-bold uppercase tracking-[0.14em] text-muted">Total</span>
        <span className="display text-xl font-semibold text-ink">{money(report.total)}</span>
      </div>
    </SectionCard>
  )
}

export default function Reports() {
  const [active, setActive] = useState('profit-loss')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let mounted = true
    Promise.all([
      api.get('/finance/reports/trial-balance'),
      api.get('/finance/reports/profit-loss'),
      api.get('/finance/reports/balance-sheet'),
      api.get('/finance/reports/receivables'),
      api.get('/finance/reports/cash-flow'),
      api.get('/finance/reports/aging'),
      api.get('/finance/reports/exceptions'),
    ])
      .then(([trial, pl, bs, ar, cash, aging, exceptions]) => {
        if (!mounted) return
        setData({ trial: trial.data, pl: pl.data, bs: bs.data, ar: ar.data, cash: cash.data, aging: aging.data, exceptions: exceptions.data })
      })
      .catch((requestError) => mounted && setError(apiErrorMessage(requestError, 'Could not load financial reports.')))
      .finally(() => mounted && setLoading(false))
    return () => {
      mounted = false
    }
  }, [])

  const totals = useMemo(() => {
    if (!data) return null
    const receivables = (data.ar ?? []).reduce((sum, row) => sum + Number(row.outstanding ?? 0), 0)
    const overdue = (data.ar ?? []).filter((row) => Number(row.days_overdue ?? 0) > 0).reduce((sum, row) => sum + Number(row.outstanding ?? 0), 0)
    return { receivables, overdue, netProfit: data.pl?.total ?? 0, cash: data.cash?.total ?? 0 }
  }, [data])

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="shimmer h-20 rounded-2xl" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => <div key={index} className="shimmer h-32 rounded-2xl" />)}
        </div>
        <div className="shimmer h-96 rounded-2xl" />
      </div>
    )
  }

  if (error) {
    return <EmptyState title="Reports unavailable" description={error} action={<button type="button" className="btn-primary" onClick={() => window.location.reload()}>Try again</button>} />
  }

  const trialTotalDebit = (data.trial ?? []).reduce((sum, row) => sum + Number(row.debit ?? 0), 0)
  const trialTotalCredit = (data.trial ?? []).reduce((sum, row) => sum + Number(row.credit ?? 0), 0)

  return (
    <>
      <PageHeader
        eyebrow="Finance"
        title="Financial reports"
        description="A faithful read of the ledger — profit, position, receivables and cash movement."
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={() => window.print()}>
              <Printer size={15} /> Print
            </button>
            <Link to="/finance/journal-entries" className="btn-primary">
              <BookOpen size={15} /> Journal entries
            </Link>
          </>
        }
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4 stagger">
        <KpiCard label="Net profit" value={money(totals.netProfit)} hint="posted income less expenses" icon={CircleDollarSign} tone="primary" />
        <KpiCard label="Receivables" value={money(totals.receivables)} hint="outstanding invoices" icon={FileText} tone="accent" />
        <KpiCard label="Overdue" value={money(totals.overdue)} hint="past due date" icon={ArrowDownRight} tone="gold" />
        <KpiCard label="Cash inflow" value={money(totals.cash)} hint="all payment methods" icon={Banknote} tone="sky" />
      </div>

      <div className="mb-5 flex gap-1 overflow-x-auto rounded-2xl border border-line bg-surface p-1.5">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActive(tab.key)}
            className={cn(
              'whitespace-nowrap rounded-xl px-4 py-2 text-xs font-bold transition',
              active === tab.key ? 'bg-primary text-forest shadow-sm' : 'text-muted hover:bg-surface-2 hover:text-ink',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {active === 'profit-loss' && (
        <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr]">
          <StatementCard title="Profit & loss statement" report={data.pl} />
          <SectionCard title="Reading the numbers" description="What this statement is telling you.">
            <div className="space-y-4 p-5">
              {(data.pl?.sections ?? []).map((section) => (
                <div key={section.label}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-ink-soft">{section.label}</span>
                    <span className="font-bold tabular-nums text-ink">{money(section.amount)}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2">
                    <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(Math.abs(Number(section.amount)) / Math.max(Math.abs(Number(data.pl?.total || 1)), 1) * 100, 100)}%` }} />
                  </div>
                </div>
              ))}
              <p className="rounded-xl bg-surface-2/70 p-3.5 text-[11px] leading-relaxed text-muted">
                Income and expenses are calculated from posted journals only. Draft journals do not affect these figures.
              </p>
            </div>
          </SectionCard>
        </div>
      )}

      {active === 'balance-sheet' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <StatementCard title="Balance sheet" report={data.bs} tone="gold" />
          <SectionCard title="Position summary" description="Assets against liabilities and equity.">
            <div className="space-y-3 p-5">
              {(data.bs?.sections ?? []).map((section) => (
                <div key={section.label} className="flex items-center justify-between rounded-xl border border-line bg-surface-2/50 px-4 py-3">
                  <span className="text-xs font-semibold text-ink-soft">{section.label}</span>
                  <span className="font-bold tabular-nums text-ink">{money(section.amount)}</span>
                </div>
              ))}
              <p className="text-[11px] leading-relaxed text-muted">
                In a balanced ledger, assets equal liabilities plus equity. Differences usually point to unposted or unbalanced journals.
              </p>
            </div>
          </SectionCard>
        </div>
      )}

      {active === 'trial-balance' && (
        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
            <div>
              <h2 className="text-sm font-bold text-ink">Trial balance</h2>
              <p className="mt-0.5 text-xs text-muted">Every account with debit, credit and net balance.</p>
            </div>
            <div className="flex items-center gap-3 text-[11px] font-semibold">
              <span className="rounded-full bg-surface-2 px-3 py-1 text-ink-soft">Dr {money(trialTotalDebit)}</span>
              <span className="rounded-full bg-surface-2 px-3 py-1 text-ink-soft">Cr {money(trialTotalCredit)}</span>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px]">
              <thead className="border-b border-line bg-surface-2/70">
                <tr>
                  <th className="th">Account</th>
                  <th className="th">Type</th>
                  <th className="th text-right">Debit</th>
                  <th className="th text-right">Credit</th>
                  <th className="th text-right">Balance</th>
                </tr>
              </thead>
              <tbody>
                {(data.trial ?? []).map((row) => (
                  <tr key={row.account_id} className="border-b border-line/70 last:border-0 hover:bg-surface-2/50">
                    <td className="td">
                      <p className="font-semibold text-ink">{row.name}</p>
                      <p className="text-[11px] text-muted">{row.code}</p>
                    </td>
                    <td className="td capitalize">{row.account_type}</td>
                    <td className="td text-right tabular-nums">{money(row.debit)}</td>
                    <td className="td text-right tabular-nums">{money(row.credit)}</td>
                    <td className="td text-right font-bold tabular-nums text-ink">{money(row.balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!(data.trial ?? []).length && <EmptyState compact icon={Scale} title="No ledger activity" description="Post journal entries to populate the trial balance." />}
          </div>
        </div>
      )}

      {active === 'receivables' && (
        <div className="card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
            <div>
              <h2 className="text-sm font-bold text-ink">Outstanding receivables</h2>
              <p className="mt-0.5 text-xs text-muted">Open customer invoices sorted by exposure.</p>
            </div>
            <span className="rounded-full bg-accent-soft px-3 py-1 text-[11px] font-bold text-accent">{money(totals.receivables)} outstanding</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px]">
              <thead className="border-b border-line bg-surface-2/70">
                <tr>
                  <th className="th">Invoice</th>
                  <th className="th">Issued</th>
                  <th className="th">Due</th>
                  <th className="th text-right">Total</th>
                  <th className="th text-right">Paid</th>
                  <th className="th text-right">Outstanding</th>
                  <th className="th text-right">Overdue</th>
                </tr>
              </thead>
              <tbody>
                {(data.ar ?? []).map((row) => (
                  <tr key={row.invoice_id} className="border-b border-line/70 last:border-0 hover:bg-surface-2/50">
                    <td className="td font-semibold text-ink">{row.invoice_number}</td>
                    <td className="td">{row.issue_date ? new Date(row.issue_date).toLocaleDateString('en-IN') : '—'}</td>
                    <td className="td">{row.due_date ? new Date(row.due_date).toLocaleDateString('en-IN') : '—'}</td>
                    <td className="td text-right tabular-nums">{money(row.total)}</td>
                    <td className="td text-right tabular-nums">{money(row.amount_paid)}</td>
                    <td className="td text-right font-bold tabular-nums text-ink">{money(row.outstanding)}</td>
                    <td className="td text-right">
                      {Number(row.days_overdue) > 0 ? (
                        <span className="badge bg-rose-50 text-rose-700 ring-rose-200">{row.days_overdue} days</span>
                      ) : (
                        <span className="badge bg-emerald-50 text-emerald-700 ring-emerald-200">Current</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!(data.ar ?? []).length && <EmptyState compact title="Nothing outstanding" description="Every posted invoice is fully collected." />}
          </div>
        </div>
      )}

      {active === 'aging' && (
        <div className="grid gap-4 lg:grid-cols-2">
          {[
            { title: 'Receivables aging', rows: data.aging?.receivables ?? [] },
            { title: 'Payables aging', rows: data.aging?.payables ?? [] },
          ].map((report) => (
            <SectionCard key={report.title} title={report.title} description="Outstanding balances grouped by due-date exposure.">
              <div className="divide-y divide-line">
                {report.rows.map((row) => (
                  <div key={row.label} className="flex items-center justify-between px-5 py-4">
                    <div>
                      <p className="text-sm font-semibold text-ink">{row.label}</p>
                      <p className="mt-0.5 text-[11px] text-muted">{row.count} open document{row.count === 1 ? '' : 's'}</p>
                    </div>
                    <span className="font-bold tabular-nums text-ink">{money(row.total)}</span>
                  </div>
                ))}
              </div>
            </SectionCard>
          ))}
        </div>
      )}

      {active === 'exceptions' && (
        <SectionCard title="Accounting exceptions" description="Items requiring follow-up before period close.">
          <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-3">
            {[
              ['Draft journals', data.exceptions?.draft_journals ?? 0, '/finance/journal-entries'],
              ['Pending approvals', data.exceptions?.pending_approvals ?? 0, '/finance/approvals'],
              ['Overdue receivables', data.exceptions?.overdue_receivables ?? 0, '/finance/reports'],
              ['Overdue payables', data.exceptions?.overdue_payables ?? 0, '/finance/vendor-payments'],
              ['Unmatched bank transactions', data.exceptions?.unmatched_bank_transactions ?? 0, '/finance/bank-reconciliation'],
              ['Open GRNI receipts', data.exceptions?.open_grni_receipts ?? 0, '/finance/reports'],
            ].map(([label, count, to]) => (
              <Link key={label} to={to} className="rounded-2xl border border-line bg-surface-2/40 p-4 transition hover:border-primary/30">
                <p className="text-xs font-semibold text-muted">{label}</p>
                <p className="mt-2 text-2xl font-bold tabular-nums text-ink">{count}</p>
              </Link>
            ))}
          </div>
        </SectionCard>
      )}

      {active === 'cash-flow' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <StatementCard title="Cash flow by method" report={data.cash} tone="gold" />
          <SectionCard title="Inflow breakdown" description="How customers are paying.">
            <div className="space-y-3 p-5">
              {(data.cash?.sections ?? []).map((section) => (
                <div key={section.label} className="flex items-center justify-between rounded-xl border border-line bg-surface-2/50 px-4 py-3">
                  <span className="text-xs font-semibold capitalize text-ink-soft">{section.label}</span>
                  <span className="font-bold tabular-nums text-ink">{money(section.amount)}</span>
                </div>
              ))}
              {!(data.cash?.sections ?? []).length && <p className="text-xs text-muted">No payments recorded yet.</p>}
              <Link to="/finance/payments" className="btn-secondary w-full">
                <Download size={14} /> View payment register
              </Link>
            </div>
          </SectionCard>
        </div>
      )}

      <p className="mt-6 text-center text-[10px] font-medium text-muted/70">
        Reports reflect posted journals only · generated {new Date().toLocaleString('en-IN')}
      </p>
    </>
  )
}
