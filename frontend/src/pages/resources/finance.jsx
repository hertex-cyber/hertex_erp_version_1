import { BookOpen, CreditCard, FileText, Landmark, Send } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { api, apiErrorMessage } from '../../lib/api'
import { Money, Primary, Ref, Status, TypeBadge } from '../../components/cells'
import { dateLabel, num } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

const INVOICE_STATUSES = ['draft', 'sent', 'paid', 'overdue', 'cancelled']
const PAYMENT_METHODS = ['bank', 'cash', 'upi', 'cheque', 'card']

export function InvoicesPage() {
  const can = useAuth((state) => state.can)

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
    <ResourcePage
      eyebrow="Finance"
      title="Invoices"
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
      searchPlaceholder="Search reference…"
      filters={[{ name: 'method', label: 'All methods', options: PAYMENT_METHODS }]}
      emptyIcon={CreditCard}
      columns={[
        { key: 'invoice_id', label: 'Invoice', render: (row) => <Ref lookup="invoices" id={row.invoice_id} /> },
        { key: 'amount', label: 'Amount', align: 'right', render: (row) => <Money value={row.amount} /> },
        { key: 'method', label: 'Method', render: (row) => <TypeBadge value={row.method} /> },
        { key: 'paid_on', label: 'Paid on', render: (row) => dateLabel(row.paid_on) },
        { key: 'reference', label: 'Reference' },
        { key: 'created_at', label: 'Recorded', render: (row) => dateLabel(row.created_at) },
      ]}
      fields={[
        { name: 'invoice_id', label: 'Invoice', type: 'reference', lookup: 'invoices', required: true },
        { name: 'amount', label: 'Amount', type: 'number', required: true },
        { name: 'method', label: 'Method', type: 'select', options: PAYMENT_METHODS, default: 'bank', required: true },
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
        { key: 'description', label: 'Description' },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'code', label: 'Account code', required: true },
        { name: 'name', label: 'Account name', required: true },
        { name: 'account_type', label: 'Account type', type: 'select', options: ACCOUNT_TYPES, required: true },
        { name: 'parent_id', label: 'Parent account', type: 'reference', lookup: 'accounts' },
        { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function JournalEntriesPage() {
  const can = useAuth((state) => state.can)

  const post = async (row, { reload }) => {
    try {
      await api.post(`/finance/journal-entries/${row.id}/post`)
      toast.success('Journal posted', `${row.entry_number} was committed to the ledger.`)
      reload()
    } catch (error) {
      toast.error('Could not post journal', apiErrorMessage(error))
    }
  }

  return (
    <ResourcePage
      eyebrow="Finance"
      title="Journal entries"
      description="Double-entry journals, balanced by construction before posting."
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
              subtitle={`${row.lines?.length ?? 0} lines · Dr ${num((row.lines ?? []).reduce((sum, line) => sum + Number(line.debit ?? 0), 0), 2)}`}
            />
          ),
        },
        { key: 'entry_date', label: 'Date', render: (row) => dateLabel(row.entry_date) },
        { key: 'memo', label: 'Memo' },
        { key: 'reference', label: 'Reference' },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'posted_at', label: 'Posted', render: (row) => dateLabel(row.posted_at) },
      ]}
      rowActions={[
        {
          label: 'Post journal',
          icon: Send,
          show: (row) => can('finance.journal.post') && row.status === 'draft',
          onClick: post,
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
      ]}
    />
  )
}
