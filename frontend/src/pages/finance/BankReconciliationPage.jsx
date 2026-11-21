import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDownUp, Check, CircleAlert, FileUp, Link2, RefreshCw, Unlink } from 'lucide-react'
import { EmptyState, KpiCard, Modal, PageHeader, Pagination, SectionCard, Spinner } from '../../components/ui'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel, money } from '../../lib/format'
import { toast } from '../../store/toast'

const PAGE_SIZE = 50

const DEFAULT_MATCH_RULES = {
  date_tolerance_days: 14,
  amount_mode: 'signed',
  reference_required: false,
  max_candidates: 20,
}

export default function BankReconciliationPage() {
  const [accounts, setAccounts] = useState([])
  const [bankAccountId, setBankAccountId] = useState('')
  const [statements, setStatements] = useState([])
  const [statementId, setStatementId] = useState('')
  const [statementSummary, setStatementSummary] = useState(null)
  const [statementReference, setStatementReference] = useState('')
  const [periodStart, setPeriodStart] = useState('')
  const [periodEnd, setPeriodEnd] = useState('')
  const [openingBalance, setOpeningBalance] = useState('0.00')
  const [closingBalance, setClosingBalance] = useState('0.00')
  const [statementSaving, setStatementSaving] = useState(false)
  const [summary, setSummary] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [candidates, setCandidates] = useState([])
  const [matchRules, setMatchRules] = useState(DEFAULT_MATCH_RULES)
  const [selectedTransaction, setSelectedTransaction] = useState(null)
  const [undoTarget, setUndoTarget] = useState(null)
  const [undoReason, setUndoReason] = useState('')
  const [undoing, setUndoing] = useState(false)
  const [file, setFile] = useState(null)
  const [filter, setFilter] = useState('unmatched')
  const [page, setPage] = useState(1)
  const [pageInfo, setPageInfo] = useState({ pages: 1, total: 0 })
  const [loading, setLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [matching, setMatching] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api.get('/finance/bank-transactions/match-rules')
      .then(({ data }) => active && setMatchRules(data))
      .catch(() => active && setMatchRules(DEFAULT_MATCH_RULES))
    api.get('/finance/bank-accounts', { params: { size: 200 } })
      .then(({ data }) => {
        if (!active) return
        const available = (data.items ?? []).filter((account) => account.is_active)
        setAccounts(available)
        setBankAccountId((current) => current || available[0]?.id || '')
      })
      .catch((requestError) => active && setError(apiErrorMessage(requestError, 'Could not load bank accounts.')))
    return () => { active = false }
  }, [])

  const load = useCallback(async () => {
    if (!bankAccountId) return
    setLoading(true)
    setError('')
    try {
      const reconciled = filter === 'all' ? undefined : filter === 'reconciled'
      const matched = filter === 'unmatched' ? false : filter === 'matched' ? true : undefined
      const [transactionsResponse, summaryResponse] = await Promise.all([
        api.get('/finance/bank-transactions', {
          params: { bank_account_id: bankAccountId, reconciled, matched, page, size: PAGE_SIZE },
        }),
        api.get(`/finance/bank-accounts/${bankAccountId}/reconciliation-summary`),
      ])
      setTransactions(transactionsResponse.data.items ?? [])
      setPageInfo({ pages: transactionsResponse.data.pages ?? 1, total: transactionsResponse.data.total ?? 0 })
      setSummary(summaryResponse.data)
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Could not load bank reconciliation.'))
    } finally {
      setLoading(false)
    }
  }, [bankAccountId, filter, page])

  useEffect(() => { load() }, [load])

  const loadStatements = useCallback(async () => {
    if (!bankAccountId) {
      setStatements([])
      setStatementId('')
      setStatementSummary(null)
      return
    }
    try {
      const { data } = await api.get('/finance/bank-statements', {
        params: { bank_account_id: bankAccountId, size: 200 },
      })
      const rows = data.items ?? []
      setStatements(rows)
      setStatementId((current) => rows.some((row) => row.id === current) ? current : '')
    } catch (requestError) {
      toast.error('Could not load bank statements', apiErrorMessage(requestError))
    }
  }, [bankAccountId])

  useEffect(() => { loadStatements() }, [loadStatements])

  useEffect(() => {
    if (!statementId) {
      setStatementSummary(null)
      return
    }
    let active = true
    api.get(`/finance/bank-statements/${statementId}/summary`)
      .then(({ data }) => active && setStatementSummary(data))
      .catch((requestError) => active && toast.error('Could not load statement balance', apiErrorMessage(requestError)))
    return () => { active = false }
  }, [statementId])

  const activeAccount = useMemo(
    () => accounts.find((account) => account.id === bankAccountId),
    [accounts, bankAccountId],
  )

  const importStatement = async (event) => {
    event.preventDefault()
    if (!bankAccountId || !file) return
    const body = new FormData()
    body.append('bank_account_id', bankAccountId)
    if (statementId) body.append('statement_id', statementId)
    body.append('file', file)
    setImporting(true)
    try {
      const { data } = await api.post('/finance/bank-transactions/import', body)
      toast.success(
        'Statement imported',
        `${data.imported} new transactions added; ${data.duplicates} duplicates skipped.`,
      )
      setFile(null)
      event.currentTarget.reset()
      setPage(1)
      await load()
      await loadStatements()
    } catch (requestError) {
      toast.error('Could not import statement', apiErrorMessage(requestError))
    } finally {
      setImporting(false)
    }
  }

  const createStatement = async (event) => {
    event.preventDefault()
    if (!bankAccountId || !statementReference.trim() || !periodStart || !periodEnd) return
    setStatementSaving(true)
    try {
      const { data } = await api.post('/finance/bank-statements', {
        bank_account_id: bankAccountId,
        statement_reference: statementReference.trim(),
        period_start: periodStart,
        period_end: periodEnd,
        opening_balance: openingBalance,
        closing_balance: closingBalance,
      })
      toast.success('Statement created', 'Matching imported lines will be attached to this statement period.')
      setStatementReference('')
      await loadStatements()
      setStatementId(data.id)
    } catch (requestError) {
      toast.error('Could not create statement', apiErrorMessage(requestError))
    } finally {
      setStatementSaving(false)
    }
  }

  const signOffStatement = async () => {
    if (!statementId || !statementSummary?.signable) return
    const reason = window.prompt('Enter the bank statement sign-off reason')
    if (!reason || reason.trim().length < 3) {
      toast.error('Sign-off reason required', 'Provide a reason of at least 3 characters.')
      return
    }
    try {
      await api.post(`/finance/bank-statements/${statementId}/sign-off`, { reason: reason.trim() })
      toast.success('Statement signed off', 'The reconciled bank statement is now locked.')
      await loadStatements()
    } catch (requestError) {
      toast.error('Could not sign off statement', apiErrorMessage(requestError))
    }
  }

  const openMatches = async (transaction) => {
    setSelectedTransaction(transaction)
    setCandidates([])
    setMatching(true)
    try {
      const { data } = await api.get(`/finance/bank-transactions/${transaction.id}/matches`)
      setCandidates(data)
    } catch (requestError) {
      toast.error('Could not load match suggestions', apiErrorMessage(requestError))
      setSelectedTransaction(null)
    } finally {
      setMatching(false)
    }
  }

  const match = async (candidate) => {
    if (!selectedTransaction) return
    try {
      await api.post(`/finance/bank-transactions/${selectedTransaction.id}/match`, {
        journal_line_id: candidate.journal_line_id,
      })
      toast.success('Transaction matched', `${candidate.entry_number} is linked to the statement line.`)
      setSelectedTransaction(null)
      await load()
    } catch (requestError) {
      toast.error('Could not match transaction', apiErrorMessage(requestError))
    }
  }

  const reconcile = async (transaction) => {
    try {
      await api.post(`/finance/bank-transactions/${transaction.id}/reconcile`)
      toast.success('Transaction reconciled', 'The bank line is now cleared against the ledger.')
      await load()
    } catch (requestError) {
      toast.error('Could not reconcile transaction', apiErrorMessage(requestError))
    }
  }

  const unmatch = async (transaction) => {
    try {
      await api.post(`/finance/bank-transactions/${transaction.id}/unmatch`)
      toast.success('Match removed', 'The unreconciled bank line is back in the exception queue.')
      await load()
    } catch (requestError) {
      toast.error('Could not remove match', apiErrorMessage(requestError))
    }
  }

  const submitUnreconcile = async (event) => {
    event.preventDefault()
    if (!undoTarget || undoReason.trim().length < 3) return
    setUndoing(true)
    try {
      await api.post(`/finance/bank-transactions/${undoTarget.id}/unreconcile`, {
        reason: undoReason.trim(),
      })
      toast.success('Reconciliation reversed', 'The statement line is matched but requires reconciliation again.')
      setUndoTarget(null)
      setUndoReason('')
      await load()
    } catch (requestError) {
      toast.error('Could not reverse reconciliation', apiErrorMessage(requestError))
    } finally {
      setUndoing(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Banking controls"
        title="Bank reconciliation"
        description="Import statement transactions, review exact ledger match suggestions, and reconcile only after matching posted journals."
        actions={
          <label className="grid gap-1 text-[11px] font-semibold text-muted">
            Bank account
            <select className="input min-w-56" value={bankAccountId} onChange={(event) => { setBankAccountId(event.target.value); setPage(1) }}>
              <option value="">Select a bank account</option>
              {accounts.map((account) => <option key={account.id} value={account.id}>{account.name} · {account.bank_name}</option>)}
            </select>
          </label>
        }
      />

      {summary && (
        <div className="mb-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard label="Imported lines" value={String(summary.imported_count)} hint={`${summary.matched_count} matched`} icon={FileUp} tone="primary" />
          <KpiCard label="Needs matching" value={String(summary.unmatched_count)} hint="Exception queue" icon={CircleAlert} tone={summary.unmatched_count ? 'gold' : 'accent'} />
          <KpiCard label="Statement net" value={money(summary.statement_balance)} hint="Imported transaction movement" icon={ArrowDownUp} tone="sky" />
          <KpiCard label="Unmatched difference" value={money(summary.difference)} hint={`Matched ledger ${money(summary.ledger_balance)}`} icon={Link2} tone={Math.abs(Number(summary.difference)) < 0.01 ? 'primary' : 'gold'} />
        </div>
      )}

      {activeAccount && !activeAccount.ledger_account_id && (
        <div className="mb-5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-800">
          Map this bank account to its active asset GL account before matching or reconciliation.
        </div>
      )}

      <SectionCard
        title="Statement period and sign-off"
        description="Record statement opening and closing balances, then sign off only when imported lines and linked journals reconcile."
        className="mb-5"
      >
        <div className="grid gap-5 p-5 xl:grid-cols-[1fr_1.2fr]">
          <div className="grid content-start gap-3">
            <label className="grid gap-1 text-[11px] font-semibold text-muted">
              Existing statement
              <select className="input" value={statementId} onChange={(event) => setStatementId(event.target.value)}>
                <option value="">No statement selected</option>
                {statements.map((statement) => (
                  <option key={statement.id} value={statement.id}>
                    {statement.statement_reference} · {statement.period_start} – {statement.period_end} · {statement.status}
                  </option>
                ))}
              </select>
            </label>
            {statementSummary && (
              <div className="rounded-xl border border-line bg-surface-2/50 p-3 text-xs">
                <div className="grid grid-cols-2 gap-2">
                  <p>Imported / reconciled: <strong>{statementSummary.imported_count} / {statementSummary.reconciled_count}</strong></p>
                  <p>Difference: <strong>{money(statementSummary.difference)}</strong></p>
                  <p>Expected close: <strong>{money(statementSummary.statement.closing_balance)}</strong></p>
                  <p>Ledger-linked close: <strong>{money(statementSummary.implied_closing_balance)}</strong></p>
                </div>
                <button
                  type="button"
                  className="btn-primary mt-3"
                  onClick={signOffStatement}
                  disabled={!statementSummary.signable || statementSummary.statement.status !== 'open'}
                >
                  {statementSummary.statement.status === 'signed_off' ? 'Signed off' : 'Sign off statement'}
                </button>
              </div>
            )}
          </div>
          <form onSubmit={createStatement} className="grid gap-3 sm:grid-cols-2">
            <label className="grid gap-1 text-[11px] font-semibold text-muted sm:col-span-2">
              Statement reference
              <input className="input" value={statementReference} onChange={(event) => setStatementReference(event.target.value)} required maxLength={120} />
            </label>
            <label className="grid gap-1 text-[11px] font-semibold text-muted">
              Period start
              <input className="input" type="date" value={periodStart} onChange={(event) => setPeriodStart(event.target.value)} required />
            </label>
            <label className="grid gap-1 text-[11px] font-semibold text-muted">
              Period end
              <input className="input" type="date" value={periodEnd} onChange={(event) => setPeriodEnd(event.target.value)} required />
            </label>
            <label className="grid gap-1 text-[11px] font-semibold text-muted">
              Opening balance
              <input className="input" type="number" step="0.01" value={openingBalance} onChange={(event) => setOpeningBalance(event.target.value)} required />
            </label>
            <label className="grid gap-1 text-[11px] font-semibold text-muted">
              Closing balance
              <input className="input" type="number" step="0.01" value={closingBalance} onChange={(event) => setClosingBalance(event.target.value)} required />
            </label>
            <button type="submit" className="btn-secondary sm:col-span-2" disabled={!bankAccountId || statementSaving}>
              {statementSaving ? 'Creating…' : 'Create statement period'}
            </button>
          </form>
        </div>
      </SectionCard>

      <div className="mb-5 grid gap-5 xl:grid-cols-[0.8fr_1.2fr]">
        <SectionCard title="Import bank statement" description="CSV columns: date, amount, description (or narration), reference (optional). Choose a statement period above to attach and validate these rows.">
          <form onSubmit={importStatement} className="grid gap-3 p-5">
            <input
              type="file"
              accept=".csv,text/csv"
              className="input file:mr-3 file:rounded-lg file:border-0 file:bg-primary-soft file:px-3 file:py-2 file:text-xs file:font-bold file:text-primary"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              required
            />
            <div className="flex items-center justify-between gap-3">
              <p className="text-[11px] leading-relaxed text-muted">Imports are idempotent per bank account. Files are limited to 10 MB and 10,000 rows.</p>
              <button type="submit" className="btn-primary shrink-0" disabled={!bankAccountId || !file || importing}>
                {importing ? <Spinner className="h-4 w-4" /> : <FileUp size={15} />}
                {importing ? 'Importing…' : 'Import CSV'}
              </button>
            </div>
          </form>
        </SectionCard>

        <SectionCard
          title="Statement transaction queue"
          description={activeAccount ? `${activeAccount.name} · ${activeAccount.currency}` : 'Choose a bank account to view statement lines.'}
          action={<button type="button" className="btn-secondary !px-3 !py-2" onClick={load} disabled={loading}><RefreshCw size={14} /> Refresh</button>}
        >
          <div className="flex gap-1 overflow-x-auto border-b border-line px-4 py-3">
            {[
              ['unmatched', 'Needs matching'],
              ['matched', 'Matched'],
              ['reconciled', 'Reconciled'],
              ['all', 'All lines'],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => { setFilter(value); setPage(1) }}
                className={`whitespace-nowrap rounded-lg px-3 py-2 text-xs font-bold ${filter === value ? 'bg-primary text-forest' : 'text-muted hover:bg-surface-2'}`}
              >
                {label}
              </button>
            ))}
          </div>
          {error ? (
            <EmptyState compact title="Reconciliation unavailable" description={error} />
          ) : loading ? (
            <div className="flex min-h-48 items-center justify-center"><Spinner /></div>
          ) : transactions.length ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[790px]">
                  <thead className="border-b border-line bg-surface-2/70">
                    <tr>
                      <th className="th">Statement line</th>
                      <th className="th">Reference</th>
                      <th className="th text-right">Amount</th>
                      <th className="th">Match</th>
                      <th className="th text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {transactions.map((transaction) => (
                      <tr key={transaction.id} className="border-b border-line/70 last:border-0 hover:bg-surface-2/50">
                        <td className="td">
                          <p className="font-semibold text-ink">{transaction.description || 'Bank transaction'}</p>
                          <p className="mt-0.5 text-[11px] text-muted">{dateLabel(transaction.txn_date)}</p>
                        </td>
                        <td className="td text-xs text-ink-soft">{transaction.reference || '—'}</td>
                        <td className={`td text-right font-bold tabular-nums ${Number(transaction.amount) >= 0 ? 'text-emerald-700' : 'text-rose-700'}`}>{money(transaction.amount)}</td>
                        <td className="td">
                          {transaction.reconciled ? (
                            <span className="badge bg-emerald-50 text-emerald-700 ring-emerald-200">Reconciled</span>
                          ) : transaction.matched_journal_line_id ? (
                            <span className="badge bg-sky-50 text-sky-700 ring-sky-200">Matched</span>
                          ) : (
                            <span className="badge bg-amber-50 text-amber-700 ring-amber-200">Unmatched</span>
                          )}
                        </td>
                        <td className="td">
                          <div className="flex justify-end gap-1.5">
                            {!transaction.reconciled && !transaction.matched_journal_line_id && (
                              <button type="button" className="btn-secondary !px-2.5 !py-1.5" onClick={() => openMatches(transaction)}><Link2 size={13} /> Match</button>
                            )}
                            {!transaction.reconciled && transaction.matched_journal_line_id && (
                              <>
                                <button type="button" className="btn-ghost !px-2 !py-1.5 text-muted" onClick={() => unmatch(transaction)} aria-label="Remove match"><Unlink size={14} /></button>
                                <button type="button" className="btn-primary !px-2.5 !py-1.5" onClick={() => reconcile(transaction)}><Check size={13} /> Reconcile</button>
                              </>
                            )}
                            {transaction.reconciled && (
                              <button type="button" className="btn-secondary !px-2.5 !py-1.5" onClick={() => { setUndoTarget(transaction); setUndoReason('') }}>
                                Undo
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination page={page} pages={pageInfo.pages} total={pageInfo.total} size={PAGE_SIZE} onPage={setPage} />
            </>
          ) : (
            <EmptyState compact icon={ArrowDownUp} title="No statement lines" description="Import a CSV statement to start matching transactions to posted journal entries." />
          )}
        </SectionCard>
      </div>

      {selectedTransaction && (
        <MatchDialog
          transaction={selectedTransaction}
          candidates={candidates}
          loading={matching}
          rules={matchRules}
          onClose={() => setSelectedTransaction(null)}
          onMatch={match}
        />
      )}
      <Modal
        open={Boolean(undoTarget)}
        onClose={() => !undoing && setUndoTarget(null)}
        title="Reverse bank reconciliation"
        description="A reason is required. The journal and its match stay unchanged; the statement line returns to the matched queue."
        size="md"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setUndoTarget(null)} disabled={undoing}>Cancel</button>
            <button type="submit" form="unreconcile-form" className="btn-primary" disabled={undoing || undoReason.trim().length < 3}>
              {undoing ? 'Reversing…' : 'Reverse reconciliation'}
            </button>
          </>
        }
      >
        <form id="unreconcile-form" onSubmit={submitUnreconcile} className="grid gap-3">
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Reason
            <textarea className="input min-h-24" value={undoReason} onChange={(event) => setUndoReason(event.target.value)} minLength={3} maxLength={500} required />
          </label>
        </form>
      </Modal>
    </>
  )
}

function MatchDialog({ transaction, candidates, loading, rules, onClose, onMatch }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-forest/50 p-0 backdrop-blur-sm sm:items-center sm:p-6">
      <button type="button" className="absolute inset-0" aria-label="Close match suggestions" onClick={onClose} />
      <div className="relative max-h-[85vh] w-full max-w-3xl overflow-hidden rounded-t-3xl border border-line bg-surface shadow-[var(--shadow-float)] sm:rounded-3xl">
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-base font-bold text-ink">Match statement line</h2>
          <p className="mt-1 text-xs text-muted">{transaction.description || 'Bank transaction'} · {dateLabel(transaction.txn_date)} · {money(transaction.amount)}</p>
          <p className="mt-1 text-[11px] text-muted">Suggestions require the same bank GL account, {rules.amount_mode === 'absolute' ? 'absolute amount' : 'signed amount'}{rules.reference_required ? ' and matching reference' : ''}, within {rules.date_tolerance_days} days. Reconciliation is a separate confirmation.</p>
        </div>
        <div className="max-h-[55vh] overflow-y-auto">
          {loading ? (
            <div className="flex min-h-36 items-center justify-center"><Spinner /></div>
          ) : candidates.length ? (
            <div className="divide-y divide-line">
              {candidates.map((candidate) => (
                <div key={candidate.journal_line_id} className="flex items-center justify-between gap-4 px-5 py-4">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-ink">{candidate.entry_number} · {candidate.memo || candidate.description || 'Journal entry'}</p>
                    <p className="mt-1 text-[11px] text-muted">{dateLabel(candidate.entry_date)}{candidate.reference ? ` · ${candidate.reference}` : ''}</p>
                  </div>
                  <button type="button" className="btn-primary shrink-0 !px-3 !py-2" onClick={() => onMatch(candidate)}>Match line</button>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState compact icon={CircleAlert} title="No exact suggestions" description={`No unmatched posted bank-ledger line has the same ${rules.amount_mode === 'absolute' ? 'absolute' : 'signed'} amount within ${rules.date_tolerance_days} days. Review the ledger or leave this line in the exception queue.`} />
          )}
        </div>
        <div className="flex justify-end border-t border-line px-5 py-3">
          <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
