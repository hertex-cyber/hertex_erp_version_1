import { useRef, useState } from 'react'
import { BadgeIndianRupee, BookOpen, CalendarRange, CreditCard, FileText, Landmark, LockKeyhole, RotateCcw, Send, UnlockKeyhole } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import GSTTaxLinesModal from './GSTTaxLinesModal'
import { Modal } from '../../components/ui'
import { api, apiErrorMessage } from '../../lib/api'
import { Money, Primary, Ref, Status, TypeBadge } from '../../components/cells'
import { dateLabel, num, today } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

const INVOICE_STATUSES = ['draft', 'sent', 'paid', 'overdue', 'cancelled']
const PAYMENT_METHODS = ['bank', 'cash', 'upi', 'cheque', 'card']

export function InvoicesPage() {
  const can = useAuth((state) => state.can)
  const [taxTarget, setTaxTarget] = useState(null)
  const [reloadList, setReloadList] = useState(null)

  const post = async (row, { reload }) => {
    try {
      await api.post(`/finance/invoices/${row.id}/post`)
      toast.success('Invoice posted', `${row.invoice_number} is now in the ledger.`)
      reload()
    } catch (error) {
      toast.error('Could not post invoice', apiErrorMessage(error))
    }
  }

  return (
    <>
    <ResourcePage
      eyebrow="Finance"
      title="Customer invoices"
      description="Receivables, posting status and collection progress."
      endpoint="/finance/invoices"
      permission="finance.invoice"
      createLabel="New invoice"
      searchPlaceholder="Search invoice numbers, notes…"
      filters={[{ name: 'status', label: 'All statuses', options: INVOICE_STATUSES }]}
      emptyIcon={FileText}
      columns={[
        { key: 'invoice_number', label: 'Invoice', render: (row) => <Primary title={row.invoice_number} subtitle={dateLabel(row.issue_date)} /> },
        { key: 'customer_id', label: 'Customer', render: (row) => <Ref lookup="customers" id={row.customer_id} /> },
        { key: 'due_date', label: 'Due', render: (row) => dateLabel(row.due_date) },
        { key: 'total', label: 'Total', align: 'right', render: (row) => <Money value={row.total} /> },
        { key: 'amount_paid', label: 'Paid', align: 'right', render: (row) => <Money value={row.amount_paid} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
      ]}
      rowActions={[
        {
          label: 'Manage GST lines',
          icon: BadgeIndianRupee,
          show: (row) => can('finance.invoice.update') && row.status === 'draft',
          onClick: (row, { reload }) => {
            setReloadList(() => reload)
            setTaxTarget(row)
          },
        },
        {
          label: 'Post to ledger',
          icon: Send,
          show: (row) => can('finance.journal.post') && row.status === 'draft',
          onClick: post,
        },
      ]}
      fields={[
        { name: 'customer_id', label: 'Customer', type: 'reference', lookup: 'customers' },
        { name: 'issue_date', label: 'Issue date', type: 'date', default: 'today', required: true },
        { name: 'due_date', label: 'Due date', type: 'date' },
        { name: 'status', label: 'Status', type: 'select', options: INVOICE_STATUSES, default: 'draft', required: true },
        { name: 'subtotal', label: 'Subtotal', type: 'number', default: 0 },
        { name: 'tax', label: 'Tax', type: 'number', default: 0 },
        { name: 'total', label: 'Total', type: 'number', default: 0 },
        { name: 'currency', label: 'Currency', default: 'INR' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
    <GSTTaxLinesModal
      open={Boolean(taxTarget)}
      invoice={taxTarget}
      invoiceType="customer"
      onClose={() => setTaxTarget(null)}
      onSaved={() => reloadList?.()}
    />
    </>
  )
}

export function PaymentsPage() {
  return (
    <ResourcePage
      eyebrow="Finance"
      title="Payments"
      description="Money received against invoices, by method and date."
      endpoint="/finance/payments"
      permission="finance.payment"
      createLabel="Record payment"
      requireIdempotencyKey
      canEdit={false}
      canDelete={false}
      searchPlaceholder="Search reference…"
      filters={[{ name: 'method', label: 'All methods', options: PAYMENT_METHODS }]}
      emptyIcon={CreditCard}
      columns={[
        { key: 'invoice_id', label: 'Invoice', render: (row) => <Ref lookup="invoices" id={row.invoice_id} /> },
        { key: 'amount', label: 'Amount', align: 'right', render: (row) => <Money value={row.amount} /> },
        { key: 'method', label: 'Method', render: (row) => <TypeBadge value={row.method} /> },
        { key: 'bank_account_id', label: 'Deposit account', render: (row) => row.bank_account_id ? <Ref lookup="bank-accounts" id={row.bank_account_id} /> : <TypeBadge value="cash" /> },
        { key: 'journal_entry_id', label: 'Ledger', render: (row) => <Status value={row.journal_entry_id ? 'posted' : 'needs review'} /> },
        { key: 'paid_on', label: 'Paid on', render: (row) => dateLabel(row.paid_on) },
        { key: 'reference', label: 'Reference' },
        { key: 'created_at', label: 'Recorded', render: (row) => dateLabel(row.created_at) },
      ]}
      fields={[
        { name: 'invoice_id', label: 'Invoice', type: 'reference', lookup: 'invoices', required: true },
        { name: 'amount', label: 'Amount', type: 'number', required: true },
        { name: 'method', label: 'Method', type: 'select', options: PAYMENT_METHODS, default: 'bank', required: true },
        { name: 'bank_account_id', label: 'Deposit account', type: 'reference', lookup: 'bank-accounts', help: 'Required for bank, UPI, card, and cheque payments; cash uses the configured cash ledger.' },
        { name: 'paid_on', label: 'Paid on', type: 'date', default: 'today', required: true },
        { name: 'reference', label: 'Reference' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

const ACCOUNT_TYPES = ['asset', 'liability', 'equity', 'income', 'expense']

export function AccountsPage() {
  return (
    <ResourcePage
      eyebrow="Finance"
      title="Chart of accounts"
      description="The ledger structure that powers journals and financial statements."
      endpoint="/finance/accounts"
      permission="finance.account"
      createLabel="New account"
      searchPlaceholder="Search codes, account names…"
      filters={[{ name: 'account_type', label: 'All types', options: ACCOUNT_TYPES }]}
      emptyIcon={BookOpen}
      columns={[
        { key: 'name', label: 'Account', render: (row) => <Primary title={row.name} subtitle={row.code} /> },
        { key: 'account_type', label: 'Type', render: (row) => <TypeBadge value={row.account_type} /> },
        { key: 'parent_id', label: 'Parent', render: (row) => <Ref lookup="accounts" id={row.parent_id} /> },
        { key: 'group_id', label: 'Group', render: (row) => <Ref lookup="account-groups" id={row.group_id} /> },
        { key: 'description', label: 'Description' },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'code', label: 'Account code', required: true },
        { name: 'name', label: 'Account name', required: true },
        { name: 'account_type', label: 'Account type', type: 'select', options: ACCOUNT_TYPES, required: true },
        { name: 'parent_id', label: 'Parent account', type: 'reference', lookup: 'accounts' },
        { name: 'group_id', label: 'Account group', type: 'reference', lookup: 'account-groups' },
        { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function AccountGroupsPage() {
  return (
    <ResourcePage
      eyebrow="Finance"
      title="Account groups"
      description="Organize ledger accounts into typed reporting groups."
      endpoint="/finance/account-groups"
      permission="finance.account"
      createLabel="New account group"
      searchPlaceholder="Search group codes and names…"
      filters={[{ name: 'account_type', label: 'All types', options: ACCOUNT_TYPES }]}
      emptyIcon={BookOpen}
      columns={[
        { key: 'name', label: 'Group', render: (row) => <Primary title={row.name} subtitle={row.code} /> },
        { key: 'account_type', label: 'Type', render: (row) => <TypeBadge value={row.account_type} /> },
        { key: 'parent_id', label: 'Parent group', render: (row) => <Ref lookup="account-groups" id={row.parent_id} /> },
        { key: 'description', label: 'Description' },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'code', label: 'Group code', required: true },
        { name: 'name', label: 'Group name', required: true },
        { name: 'account_type', label: 'Account type', type: 'select', options: ACCOUNT_TYPES, required: true },
        { name: 'parent_id', label: 'Parent group', type: 'reference', lookup: 'account-groups' },
        { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function JournalEntriesPage() {
  const can = useAuth((state) => state.can)
  const [reversalTarget, setReversalTarget] = useState(null)
  const [reversalDate, setReversalDate] = useState(today())
  const [reversalReason, setReversalReason] = useState('')
  const [reversing, setReversing] = useState(false)
  const reloadRef = useRef(() => {})

  const post = async (row, { reload }) => {
    try {
      await api.post(`/finance/journal-entries/${row.id}/post`)
      toast.success('Journal submitted', `${row.entry_number} is awaiting approval from another user.`)
      reload()
    } catch (error) {
      toast.error('Could not submit journal', apiErrorMessage(error))
    }
  }

  const submitReversal = async () => {
    if (!reversalTarget || reversalReason.trim().length < 3) return
    setReversing(true)
    try {
      const { data } = await api.post(
        `/finance/journal-entries/${reversalTarget.id}/reverse`,
        { reversal_date: reversalDate, reason: reversalReason.trim() },
      )
      toast.success('Journal reversed', `${reversalTarget.entry_number} reversed as ${data.entry_number}.`)
      setReversalTarget(null)
      setReversalReason('')
      await reloadRef.current()
    } catch (error) {
      toast.error('Could not reverse journal', apiErrorMessage(error))
    } finally {
      setReversing(false)
    }
  }

  return (
    <>
      <ResourcePage
        eyebrow="Finance"
        title="Journal entries"
        description="Double-entry journals are submitted for independent approval before posting to the ledger."
        endpoint="/finance/journal-entries"
        permission="finance.journalentry"
        createLabel="New journal entry"
        searchPlaceholder="Search journals…"
        filters={[{ name: 'status', label: 'All statuses', options: ['draft', 'posted'] }]}
        canEdit={false}
        canDelete={false}
        emptyIcon={BookOpen}
        columns={[
          {
            key: 'entry_number',
            label: 'Journal',
            render: (row) => (
              <Primary
                title={row.entry_number}
                subtitle={`${row.lines?.length ?? 0} lines · Dr ${num((row.lines ?? []).reduce((sum, line) => sum + Number(line.debit ?? 0), 0), 2)}${row.approval_status === 'pending' ? ' · Awaiting approval' : ''}`}
              />
            ),
          },
          { key: 'entry_date', label: 'Date', render: (row) => dateLabel(row.entry_date) },
          { key: 'memo', label: 'Memo' },
          { key: 'reference', label: 'Reference' },
          { key: 'status', label: 'Status', render: (row) => <Status value={row.reversed_by_entry_id ? 'reversed' : row.approval_status === 'pending' ? 'pending approval' : row.status} /> },
          { key: 'posted_at', label: 'Posted', render: (row) => dateLabel(row.posted_at) },
        ]}
        rowActions={[
          {
            label: 'Submit for approval',
            icon: Send,
            show: (row) => can('finance.journal.post') && row.status === 'draft' && row.approval_status !== 'pending',
            onClick: post,
          },
          {
            label: 'Reverse journal',
            icon: RotateCcw,
            show: (row) =>
              can('finance.journal.reverse')
              && row.status === 'posted'
              && !row.reversal_of_id
              && !row.reversed_by_entry_id,
            onClick: (row, options) => {
              reloadRef.current = options.reload
              setReversalTarget(row)
              setReversalDate(today())
              setReversalReason('')
            },
          },
        ]}
        fields={[
          { name: 'entry_date', label: 'Entry date', type: 'date', default: 'today', required: true },
          { name: 'reference', label: 'Reference' },
          { name: 'memo', label: 'Memo', type: 'textarea', colSpan: 2 },
          {
            name: 'lines',
            label: 'Journal lines',
            type: 'line_items',
            required: true,
            initialRows: 2,
            columns: [
              { name: 'account_id', label: 'Account', type: 'reference', lookup: 'accounts', required: true, flex: 2 },
              { name: 'description', label: 'Description', type: 'text', flex: 2 },
              { name: 'debit', label: 'Debit', type: 'number', default: 0, width: 'w-24' },
              { name: 'credit', label: 'Credit', type: 'number', default: 0, width: 'w-24' },
            ],
          },
        ]}
      />
      <Modal
        open={Boolean(reversalTarget)}
        onClose={() => !reversing && setReversalTarget(null)}
        title="Reverse posted journal"
        description={reversalTarget ? `Create an opposite journal for ${reversalTarget.entry_number}. The posted entry remains unchanged.` : ''}
        size="md"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setReversalTarget(null)} disabled={reversing}>
              Cancel
            </button>
            <button type="button" className="btn-primary" onClick={submitReversal} disabled={reversing || reversalReason.trim().length < 3 || !reversalDate}>
              {reversing ? 'Reversing…' : 'Create reversal'}
            </button>
          </>
        }
      >
        <div className="grid gap-4">
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Reversal date
            <input className="input" type="date" value={reversalDate} onChange={(event) => setReversalDate(event.target.value)} required />
          </label>
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Reason
            <textarea className="input min-h-24" value={reversalReason} onChange={(event) => setReversalReason(event.target.value)} minLength={3} maxLength={500} required />
          </label>
        </div>
      </Modal>
    </>
  )
}

export function PeriodsPage() {
  const can = useAuth((state) => state.can)

  const changeStatus = async (row, status, { reload }) => {
    const action = status === 'closed' ? 'close' : 'reopen'
    try {
      if (status === 'closed') {
        const reason = window.prompt('Enter the period close sign-off reason')
        if (!reason || reason.trim().length < 3) {
          toast.error('Close sign-off required', 'Provide a reason of at least 3 characters.')
          return
        }
        await api.post(`/finance/periods/${row.id}/sign-off`, { reason: reason.trim() })
      }
      await api.post(`/finance/periods/${row.id}/${action}`)
      toast.success(
        status === 'closed' ? 'Period closed' : 'Period reopened',
        `${row.name} is now ${status}.`,
      )
      reload()
    } catch (error) {
      toast.error(
        status === 'closed' ? 'Could not close period' : 'Could not reopen period',
        apiErrorMessage(error),
      )
    }
  }

  return (
    <ResourcePage
      eyebrow="Finance"
      title="Financial periods"
      description="Define posting windows and close periods to lock their dates in the ledger. Once configured, only dates within an open period may post."
      endpoint="/finance/periods"
      permission="finance.fiscalperiod"
      createLabel="New period"
      searchPlaceholder="Search periods…"
      canEdit={false}
      canDelete={false}
      emptyIcon={CalendarRange}
      columns={[
        { key: 'name', label: 'Period', render: (row) => <Primary title={row.name} subtitle={`${dateLabel(row.start_date)} – ${dateLabel(row.end_date)}`} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'closed_at', label: 'Closed', render: (row) => dateLabel(row.closed_at) },
        { key: 'close_signed_at', label: 'Sign-off', render: (row) => row.close_signed_at ? <Status value="signed off" /> : <Status value="unsigned" /> },
      ]}
      rowActions={[
        {
          label: 'Close period',
          icon: LockKeyhole,
          show: (row) => can('finance.period.close') && row.status === 'open',
          onClick: (row, options) => changeStatus(row, 'closed', options),
        },
        {
          label: 'Reopen period',
          icon: UnlockKeyhole,
          show: (row) => can('finance.period.reopen') && row.status === 'closed',
          onClick: (row, options) => changeStatus(row, 'open', options),
        },
      ]}
      fields={[
        { name: 'name', label: 'Period name', required: true },
        { name: 'start_date', label: 'Start date', type: 'date', required: true },
        { name: 'end_date', label: 'End date', type: 'date', required: true },
      ]}
    />
  )
}

export function BankAccountsPage() {
  return (
    <ResourcePage
      eyebrow="Finance"
      title="Bank accounts"
      description="Operating accounts and opening balances used for reconciliation."
      endpoint="/finance/bank-accounts"
      permission="finance.bankaccount"
      createLabel="New bank account"
      searchPlaceholder="Search banks, account numbers…"
      emptyIcon={Landmark}
      columns={[
        { key: 'name', label: 'Account', render: (row) => <Primary title={row.name} subtitle={row.bank_name} /> },
        { key: 'account_number', label: 'Account number', render: (row) => `•••• ${String(row.account_number ?? '').slice(-4)}` },
        { key: 'ledger_account_id', label: 'GL mapping', render: (row) => <Ref lookup="accounts" id={row.ledger_account_id} /> },
        { key: 'opening_balance', label: 'Opening balance', align: 'right', render: (row) => <Money value={row.opening_balance} /> },
        { key: 'currency', label: 'Currency', render: (row) => <TypeBadge value={row.currency} /> },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'name', label: 'Account name', required: true },
        { name: 'bank_name', label: 'Bank name', required: true },
        { name: 'account_number', label: 'Account number', required: true },
        { name: 'opening_balance', label: 'Opening balance', type: 'number', default: 0 },
        { name: 'currency', label: 'Currency', default: 'INR' },
        { name: 'ledger_account_id', label: 'GL account', type: 'reference', lookup: 'accounts', help: 'Map to the active asset account used when receipts are posted.' },
      ]}
    />
  )
}
