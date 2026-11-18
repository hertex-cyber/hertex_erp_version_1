import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDownToLine, CircleAlert, CreditCard, Landmark, RefreshCw, Wallet } from 'lucide-react'
import { EmptyState, Modal, PageHeader, Pagination, SearchInput, SectionCard, Spinner } from '../../components/ui'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel, money, today } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

const PAGE_SIZE = 25

export default function VendorPaymentsPage() {
  const can = useAuth((state) => state.can)
  const canReadBankAccounts = can('finance.bankaccount.read')
  const [payables, setPayables] = useState([])
  const [payments, setPayments] = useState([])
  const [bankAccounts, setBankAccounts] = useState([])
  const [payableSummary, setPayableSummary] = useState({ bill_count: 0, outstanding_total: 0 })
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)
  const [pageInfo, setPageInfo] = useState({ pages: 1, total: 0 })
  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState('')
  const [selected, setSelected] = useState(null)
  const [method, setMethod] = useState('bank')
  const [bankAccountId, setBankAccountId] = useState('')
  const [amount, setAmount] = useState('')
  const [paidOn, setPaidOn] = useState(today())
  const [reference, setReference] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const idempotencyKey = useRef('')

  const load = useCallback(async () => {
    setLoading(true)
    setPageError('')
    try {
      const [outstanding, summary, history, banks] = await Promise.all([
        api.get('/finance/vendor-payments/outstanding', { params: { page, size: PAGE_SIZE, q: query || undefined } }),
        api.get('/finance/vendor-payments/summary'),
        api.get('/finance/vendor-payments', { params: { size: PAGE_SIZE } }),
        canReadBankAccounts
          ? api.get('/finance/bank-accounts', { params: { size: 200 } })
          : Promise.resolve({ data: { items: [] } }),
      ])
      setPayables(outstanding.data.items ?? [])
      setPageInfo({ pages: outstanding.data.pages ?? 1, total: outstanding.data.total ?? 0 })
      setPayableSummary(summary.data)
      setPayments(history.data.items ?? [])
      setBankAccounts((banks.data.items ?? []).filter((account) => account.is_active && account.ledger_account_id))
    } catch (error) {
      setPageError(apiErrorMessage(error, 'Could not load accounts payable.'))
    } finally {
      setLoading(false)
    }
  }, [canReadBankAccounts, page, query])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPage(1)
      setQuery(search.trim())
    }, 250)
    return () => window.clearTimeout(timer)
  }, [search])

  const summary = useMemo(() => ({
    outstanding: payableSummary.outstanding_total,
    bills: payableSummary.bill_count,
    recentPayments: payments.length,
  }), [payableSummary, payments])

  const openPayment = (invoice) => {
    setSelected(invoice)
    setAmount(String(invoice.outstanding))
    setMethod(canReadBankAccounts ? 'bank' : 'cash')
    setBankAccountId(bankAccounts[0]?.id ?? '')
    setPaidOn(today())
    setReference('')
    idempotencyKey.current = ''
  }

  const submit = async (event) => {
    event.preventDefault()
    if (!selected || !amount || Number(amount) <= 0) return
    if (method !== 'cash' && !bankAccountId) {
      toast.error('Bank account required', 'Map and select an active bank account before posting this disbursement.')
      return
    }
    if (!idempotencyKey.current) idempotencyKey.current = crypto.randomUUID()
    setSubmitting(true)
    try {
      await api.post(
        '/finance/vendor-payments',
        {
          vendor_invoice_id: selected.invoice_id,
          amount,
          method,
          bank_account_id: method === 'cash' ? null : bankAccountId,
          paid_on: paidOn,
          reference: reference.trim() || null,
        },
        { headers: { 'Idempotency-Key': idempotencyKey.current } },
      )
      toast.success('Vendor payment submitted', `${selected.invoice_number} is awaiting approval from another user.`)
      setSelected(null)
      idempotencyKey.current = ''
      await load()
    } catch (error) {
      toast.error('Could not post vendor payment', apiErrorMessage(error))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Accounts payable"
        title="Vendor payments"
        description="Review approved bills, submit bank or cash disbursement requests, and track their approval status."
        actions={<button type="button" className="btn-secondary" onClick={load} disabled={loading}><RefreshCw size={15} /> Refresh</button>}
      />

      <div className="mb-5 grid gap-4 sm:grid-cols-3">
        <SummaryCard icon={ArrowDownToLine} label="Open payables" value={money(summary.outstanding)} hint={`${summary.bills} approved bills`} />
        <SummaryCard icon={CreditCard} label="Recent requests" value={String(summary.recentPayments)} hint="Latest disbursement requests" />
        <SummaryCard
          icon={Landmark}
          label={canReadBankAccounts ? 'Mapped bank accounts' : 'Bank access'}
          value={canReadBankAccounts ? String(bankAccounts.length) : 'Restricted'}
          hint={canReadBankAccounts ? 'Active, ledger-linked accounts' : 'Cash settlement remains available'}
        />
      </div>

      {pageError ? (
        <EmptyState icon={CircleAlert} title="Could not load payables" description={pageError} action={<button className="btn-primary" onClick={load} type="button">Try again</button>} />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
          <SectionCard title="Bills ready for payment" description="Approved invoices with an outstanding balance.">
            <div className="border-b border-line px-4 py-3">
              <SearchInput value={search} onChange={setSearch} placeholder="Search vendors or invoice numbers…" />
            </div>
            {loading ? (
              <div className="flex min-h-48 items-center justify-center gap-3 text-sm text-muted"><Spinner /> Loading payables…</div>
            ) : payables.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px]">
                  <thead className="border-b border-line bg-surface-2/70">
                    <tr>
                      <th className="th">Vendor bill</th>
                      <th className="th">Due</th>
                      <th className="th text-right">Total</th>
                      <th className="th text-right">Outstanding</th>
                      <th className="th">Status</th>
                      <th className="th" />
                    </tr>
                  </thead>
                  <tbody>
                    {payables.map((invoice) => (
                      <tr key={invoice.invoice_id} className="border-b border-line/70 last:border-0 hover:bg-surface-2/50">
                        <td className="td">
                          <p className="font-semibold text-ink">{invoice.invoice_number}</p>
                          <p className="mt-0.5 text-[11px] text-muted">{invoice.vendor_name}</p>
                        </td>
                        <td className="td">{dateLabel(invoice.due_date)}</td>
                        <td className="td text-right tabular-nums">{money(invoice.total)}</td>
                        <td className="td text-right font-bold tabular-nums text-ink">{money(invoice.outstanding)}</td>
                        <td className="td"><span className="badge bg-amber-50 text-amber-700 ring-amber-200">{invoice.status === 'partially_paid' ? 'Partially paid' : 'Approved'}</span></td>
                        <td className="td text-right">
                          <button type="button" className="btn-primary !px-3 !py-2" onClick={() => openPayment(invoice)}>Pay bill</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Pagination
                  page={page}
                  pages={pageInfo.pages}
                  total={pageInfo.total}
                  size={PAGE_SIZE}
                  onPage={setPage}
                />
              </div>
            ) : (
              <EmptyState compact icon={Wallet} title="No open vendor bills" description="Approved vendor invoices with an outstanding balance will appear here." />
            )}
          </SectionCard>

          <SectionCard title="Recent disbursements" description="Approved payments link to posted journals; pending requests do not change balances.">
            {loading ? (
              <div className="flex min-h-48 items-center justify-center"><Spinner /></div>
            ) : payments.length ? (
              <div className="divide-y divide-line">
                {payments.slice(0, 8).map((payment) => (
                  <div key={payment.id} className="flex items-center justify-between gap-3 px-5 py-3.5">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-ink">{payment.reference || 'Vendor invoice payment'}</p>
                      <p className="mt-0.5 text-[11px] capitalize text-muted">{payment.method} · {dateLabel(payment.paid_on)}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-sm font-bold tabular-nums text-ink">{money(payment.amount)}</p>
                      <p className={`mt-0.5 text-[10px] font-semibold ${payment.status === 'posted' ? 'text-emerald-700' : payment.status === 'rejected' ? 'text-rose-700' : 'text-amber-700'}`}>
                        {payment.status === 'posted' ? 'Posted' : payment.status === 'rejected' ? 'Rejected' : 'Pending approval'}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState compact icon={CreditCard} title="No disbursements yet" description="Settled vendor payments will be listed here." />
            )}
          </SectionCard>
        </div>
      )}

      <Modal
        open={Boolean(selected)}
        onClose={() => !submitting && setSelected(null)}
        title="Request vendor payment"
        description={selected ? `${selected.vendor_name} · ${selected.invoice_number} · ${money(selected.outstanding)} outstanding` : ''}
        size="md"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setSelected(null)} disabled={submitting}>Cancel</button>
            <button type="submit" form="vendor-payment-form" className="btn-primary" disabled={submitting || !amount || Number(amount) <= 0}>
              {submitting ? 'Submitting…' : 'Submit for approval'}
            </button>
          </>
        }
      >
        <form id="vendor-payment-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Payment amount
            <input className="input" type="number" min="0.01" max={selected?.outstanding} step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} required />
            <span className="text-[11px] font-normal text-muted">Cannot exceed {money(selected?.outstanding)} outstanding.</span>
          </label>
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Payment date
            <input className="input" type="date" value={paidOn} onChange={(event) => setPaidOn(event.target.value)} required />
          </label>
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Method
            <select className="input" value={method} onChange={(event) => setMethod(event.target.value)}>
              {canReadBankAccounts && <option value="bank">Bank transfer</option>}
              {canReadBankAccounts && <option value="upi">UPI</option>}
              {canReadBankAccounts && <option value="cheque">Cheque</option>}
              <option value="cash">Cash</option>
            </select>
          </label>
          {method !== 'cash' && (
            <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
              Paying bank account
              <select className="input" value={bankAccountId} onChange={(event) => setBankAccountId(event.target.value)} required>
                <option value="">Select a mapped bank account</option>
                {bankAccounts.map((account) => <option key={account.id} value={account.id}>{account.name} · {account.bank_name}</option>)}
              </select>
              {!bankAccounts.length && <span className="text-[11px] font-normal text-rose-700">Add a bank account and map it to an active asset GL account first.</span>}
            </label>
          )}
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft sm:col-span-2">
            Bank / cheque reference
            <input className="input" maxLength={120} value={reference} onChange={(event) => setReference(event.target.value)} placeholder="Transaction or cheque number" />
          </label>
        </form>
      </Modal>
    </>
  )
}

function SummaryCard({ icon: Icon, label, value, hint }) {
  return (
    <div className="card flex items-start justify-between gap-3 p-5">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-muted">{label}</p>
        <p className="display mt-2 text-2xl font-semibold text-ink">{value}</p>
        <p className="mt-2 text-xs text-muted">{hint}</p>
      </div>
      <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary-soft text-primary"><Icon size={18} /></span>
    </div>
  )
}
