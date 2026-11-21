import { useEffect, useState } from 'react'
import { Archive, BadgeIndianRupee, Ban, Calculator, Landmark } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { Modal } from '../../components/ui'
import { Money, Primary, Ref, Status } from '../../components/cells'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel, today } from '../../lib/format'
import { toast } from '../../store/toast'

export default function FixedAssetsPage() {
  const [accounts, setAccounts] = useState([])
  const [depreciationOpen, setDepreciationOpen] = useState(false)
  const [capitalizationTarget, setCapitalizationTarget] = useState(null)
  const [disposalTarget, setDisposalTarget] = useState(null)
  const [impairmentTarget, setImpairmentTarget] = useState(null)
  const [writeOffTarget, setWriteOffTarget] = useState(null)
  const [resourceKey, setResourceKey] = useState(0)
  const [creditAccountId, setCreditAccountId] = useState('')
  const [proceedsAccountId, setProceedsAccountId] = useState('')
  const [gainLossAccountId, setGainLossAccountId] = useState('')
  const [proceeds, setProceeds] = useState('0.00')
  const [disposedOn, setDisposedOn] = useState(today())
  const [impairmentDate, setImpairmentDate] = useState(today())
  const [impairmentLoss, setImpairmentLoss] = useState('0.00')
  const [expenseAccountId, setExpenseAccountId] = useState('')
  const [impairmentReason, setImpairmentReason] = useState('')
  const [writeOffDate, setWriteOffDate] = useState(today())
  const [writeOffReason, setWriteOffReason] = useState('')
  const [depreciationPeriod, setDepreciationPeriod] = useState(today())
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get('/finance/accounts', { params: { size: 200 } })
      .then(({ data }) => setAccounts((data.items ?? []).filter((account) => account.is_active)))
      .catch((error) => toast.error('Could not load ledger accounts', apiErrorMessage(error)))
  }, [])

  const openCapitalization = (asset) => {
    setCapitalizationTarget(asset)
    setCreditAccountId('')
  }

  const capitalize = async () => {
    if (!creditAccountId) return
    setBusy(true)
    try {
      await api.post(`/finance/assets/${capitalizationTarget.id}/capitalize`, { credit_account_id: creditAccountId })
      toast.success('Asset capitalized', 'The acquisition journal was posted to the ledger.')
      setCapitalizationTarget(null)
      setResourceKey((current) => current + 1)
    } catch (error) {
      toast.error('Could not capitalize asset', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const runDepreciation = async () => {
    if (!depreciationPeriod) return
    setBusy(true)
    try {
      const { data } = await api.post('/finance/assets/depreciation/run', { period_end: depreciationPeriod })
      toast.success(
        'Depreciation run complete',
        `${data.created_count} posted; ${data.skipped_count} already posted or not yet depreciable.`,
      )
      setDepreciationOpen(false)
      setResourceKey((current) => current + 1)
    } catch (error) {
      toast.error('Could not run depreciation', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const openDisposal = (asset) => {
    setDisposalTarget(asset)
    setDisposedOn(today())
    setProceeds('0.00')
    setProceedsAccountId('')
    setGainLossAccountId('')
  }

  const dispose = async () => {
    if (!proceedsAccountId || !gainLossAccountId || !disposedOn) return
    setBusy(true)
    try {
      await api.post(`/finance/assets/${disposalTarget.id}/dispose`, {
        disposed_on: disposedOn,
        proceeds: proceeds,
        proceeds_account_id: proceedsAccountId,
        gain_loss_account_id: gainLossAccountId,
      })
      toast.success('Asset disposed', 'The disposal journal was posted to the ledger.')
      setDisposalTarget(null)
      setResourceKey((current) => current + 1)
    } catch (error) {
      toast.error('Could not dispose asset', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const openImpairment = (asset) => {
    setImpairmentTarget(asset)
    setImpairmentDate(today())
    setImpairmentLoss('0.00')
    setExpenseAccountId('')
    setImpairmentReason('')
  }

  const impair = async () => {
    if (!expenseAccountId || !impairmentDate || !impairmentReason) return
    setBusy(true)
    try {
      await api.post(`/finance/assets/${impairmentTarget.id}/impair`, {
        impairment_date: impairmentDate,
        impairment_loss: impairmentLoss,
        expense_account_id: expenseAccountId,
        reason: impairmentReason,
      })
      toast.success('Asset impaired', 'The impairment journal was posted to the ledger.')
      setImpairmentTarget(null)
      setResourceKey((current) => current + 1)
    } catch (error) {
      toast.error('Could not impair asset', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const openWriteOff = (asset) => {
    setWriteOffTarget(asset)
    setWriteOffDate(today())
    setWriteOffReason('')
  }

  const writeOff = async () => {
    if (!writeOffDate || !writeOffReason) return
    setBusy(true)
    try {
      await api.post(`/finance/assets/${writeOffTarget.id}/write-off`, {
        write_off_date: writeOffDate,
        reason: writeOffReason,
      })
      toast.success('Asset written off', 'The write-off journal was posted to the ledger.')
      setWriteOffTarget(null)
      setResourceKey((current) => current + 1)
    } catch (error) {
      toast.error('Could not write off asset', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const accountOptions = (filter) => accounts.filter(filter)
  const assetAccounts = accountOptions((account) => account.account_type === 'asset')
  const creditAccounts = accountOptions((account) => ['asset', 'liability'].includes(account.account_type))
  const impairmentAccounts = accountOptions((account) => account.account_type === 'expense')
  const gainLossAccounts = accountOptions((account) => ['income', 'expense'].includes(account.account_type))

  return (
    <>
      <div className="mb-4 flex justify-end">
        <button type="button" className="btn-secondary" onClick={() => { setDepreciationPeriod(today()); setDepreciationOpen(true) }}>
          <Calculator size={15} /> Run depreciation
        </button>
      </div>
      <ResourcePage
        key={resourceKey}
        eyebrow="Finance"
        title="Fixed assets"
        description="Capitalize acquisitions, run straight-line depreciation, record impairment, write-offs and disposals."
        endpoint="/finance/assets"
        permission="finance.asset"
        createLabel="Register asset"
        searchPlaceholder="Search asset tag or name…"
        filters={[
          {
            name: 'status',
            label: 'All statuses',
            options: ['draft', 'active', 'impaired', 'disposed', 'written_off'],
          },
        ]}
        columns={[
          { key: 'name', label: 'Asset', render: (row) => <Primary title={row.name} subtitle={row.asset_tag} /> },
          { key: 'cost', label: 'Cost', align: 'right', render: (row) => <Money value={row.cost} /> },
          { key: 'accumulated_depreciation', label: 'Depreciated', align: 'right', render: (row) => <Money value={row.accumulated_depreciation} /> },
          { key: 'impairment_loss', label: 'Impairment', align: 'right', render: (row) => <Money value={row.impairment_loss} /> },
          { key: 'asset_account_id', label: 'Asset account', render: (row) => <Ref lookup="accounts" id={row.asset_account_id} /> },
          { key: 'acquisition_date', label: 'Acquired', render: (row) => dateLabel(row.acquisition_date) },
          { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        ]}
        rowActions={[
          {
            label: 'Capitalize',
            icon: Landmark,
            show: (row) => row.status === 'draft',
            onClick: openCapitalization,
          },
          {
            label: 'Impair',
            icon: BadgeIndianRupee,
            show: (row) => ['active', 'impaired'].includes(row.status),
            onClick: openImpairment,
          },
          {
            label: 'Write off',
            icon: Ban,
            show: (row) => ['active', 'impaired'].includes(row.status),
            onClick: openWriteOff,
          },
          {
            label: 'Dispose',
            icon: Archive,
            show: (row) => ['active', 'impaired'].includes(row.status),
            onClick: openDisposal,
          },
        ]}
        fields={[
          { name: 'asset_tag', label: 'Asset tag', required: true },
          { name: 'name', label: 'Asset name', required: true },
          { name: 'acquisition_date', label: 'Acquisition date', type: 'date', default: 'today', required: true },
          { name: 'in_service_date', label: 'In-service date', type: 'date', default: 'today', required: true },
          { name: 'cost', label: 'Acquisition cost', type: 'number', required: true },
          { name: 'residual_value', label: 'Residual value', type: 'number', default: 0 },
          { name: 'useful_life_months', label: 'Useful life (months)', type: 'number', required: true },
          { name: 'asset_account_id', label: 'Fixed asset account', type: 'reference', lookup: 'accounts', required: true },
          { name: 'accumulated_depreciation_account_id', label: 'Accumulated depreciation account', type: 'reference', lookup: 'accounts', required: true },
          { name: 'depreciation_expense_account_id', label: 'Depreciation expense account', type: 'reference', lookup: 'accounts', required: true },
          { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
        ]}
      />
      <Modal
        open={depreciationOpen}
        onClose={() => !busy && setDepreciationOpen(false)}
        title="Run monthly depreciation"
        description="Select the final calendar day of the month. Straight-line depreciation starts in the month after the in-service date."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setDepreciationOpen(false)} disabled={busy}>Close</button>
            <button type="button" className="btn-primary" onClick={runDepreciation} disabled={busy || !depreciationPeriod}>
              {busy ? 'Posting…' : 'Post depreciation'}
            </button>
          </>
        }
      >
        <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
          Period end
          <input className="input" type="date" value={depreciationPeriod} onChange={(event) => setDepreciationPeriod(event.target.value)} />
        </label>
      </Modal>
      <Modal
        open={Boolean(capitalizationTarget)}
        onClose={() => !busy && setCapitalizationTarget(null)}
        title="Capitalize fixed asset"
        description={capitalizationTarget ? `Post the acquisition value for ${capitalizationTarget.asset_tag}.` : ''}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setCapitalizationTarget(null)} disabled={busy}>Cancel</button>
            <button type="button" className="btn-primary" onClick={capitalize} disabled={busy || !creditAccountId}>
              {busy ? 'Posting…' : 'Post acquisition'}
            </button>
          </>
        }
      >
        <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
          Credit account (AP, bank, or clearing)
          <select className="input" value={creditAccountId} onChange={(event) => setCreditAccountId(event.target.value)}>
            <option value="">Select account</option>
            {creditAccounts.map((account) => <option key={account.id} value={account.id}>{account.code} · {account.name}</option>)}
          </select>
        </label>
      </Modal>
      <Modal
        open={Boolean(disposalTarget)}
        onClose={() => !busy && setDisposalTarget(null)}
        title="Dispose fixed asset"
        description={disposalTarget ? `Remove ${disposalTarget.asset_tag} from service and post any gain or loss.` : ''}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setDisposalTarget(null)} disabled={busy}>Cancel</button>
            <button type="button" className="btn-primary" onClick={dispose} disabled={busy || !proceedsAccountId || !gainLossAccountId}>
              {busy ? 'Posting…' : 'Post disposal'}
            </button>
          </>
        }
      >
        <div className="grid gap-4">
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Disposal date
            <input className="input" type="date" value={disposedOn} onChange={(event) => setDisposedOn(event.target.value)} />
          </label>
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Proceeds
            <input className="input" type="number" min="0" step="0.01" value={proceeds} onChange={(event) => setProceeds(event.target.value)} />
          </label>
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Proceeds account
            <select className="input" value={proceedsAccountId} onChange={(event) => setProceedsAccountId(event.target.value)}>
              <option value="">Select account</option>
              {assetAccounts.map((account) => <option key={account.id} value={account.id}>{account.code} · {account.name}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Gain/loss account
            <select className="input" value={gainLossAccountId} onChange={(event) => setGainLossAccountId(event.target.value)}>
              <option value="">Select account</option>
              {gainLossAccounts.map((account) => <option key={account.id} value={account.id}>{account.code} · {account.name} ({account.account_type})</option>)}
            </select>
          </label>
        </div>
      </Modal>
      <Modal
        open={Boolean(impairmentTarget)}
        onClose={() => !busy && setImpairmentTarget(null)}
        title="Impair fixed asset"
        description={impairmentTarget ? `Recognise a decline in value for ${impairmentTarget.asset_tag}.` : ''}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setImpairmentTarget(null)} disabled={busy}>Cancel</button>
            <button type="button" className="btn-primary" onClick={impair} disabled={busy || !expenseAccountId || !impairmentReason}>
              {busy ? 'Posting…' : 'Post impairment'}
            </button>
          </>
        }
      >
        <div className="grid gap-4">
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Impairment date
            <input className="input" type="date" value={impairmentDate} onChange={(event) => setImpairmentDate(event.target.value)} />
          </label>
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Impairment loss
            <input className="input" type="number" min="0.01" step="0.01" value={impairmentLoss} onChange={(event) => setImpairmentLoss(event.target.value)} />
          </label>
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Expense account
            <select className="input" value={expenseAccountId} onChange={(event) => setExpenseAccountId(event.target.value)}>
              <option value="">Select account</option>
              {impairmentAccounts.map((account) => <option key={account.id} value={account.id}>{account.code} · {account.name}</option>)}
            </select>
          </label>
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Reason
            <textarea className="input min-h-24" value={impairmentReason} onChange={(event) => setImpairmentReason(event.target.value)} />
          </label>
        </div>
      </Modal>
      <Modal
        open={Boolean(writeOffTarget)}
        onClose={() => !busy && setWriteOffTarget(null)}
        title="Write off fixed asset"
        description={writeOffTarget ? `Remove ${writeOffTarget.asset_tag} and post its remaining carrying value.` : ''}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setWriteOffTarget(null)} disabled={busy}>Cancel</button>
            <button type="button" className="btn-primary" onClick={writeOff} disabled={busy || !writeOffReason}>
              {busy ? 'Posting…' : 'Post write-off'}
            </button>
          </>
        }
      >
        <div className="grid gap-4">
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Write-off date
            <input className="input" type="date" value={writeOffDate} onChange={(event) => setWriteOffDate(event.target.value)} />
          </label>
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Reason
            <textarea className="input min-h-24" value={writeOffReason} onChange={(event) => setWriteOffReason(event.target.value)} />
          </label>
        </div>
      </Modal>
    </>
  )
}
