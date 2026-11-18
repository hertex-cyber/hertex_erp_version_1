import { useCallback, useEffect, useState } from 'react'
import { BadgeCheck, CircleAlert, Plus, RefreshCw, ShieldCheck } from 'lucide-react'
import { PageHeader, SectionCard, Spinner } from '../../components/ui'
import { api, apiErrorMessage } from '../../lib/api'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

const EMPTY_REGISTRATION = {
  legal_name: '',
  gstin: '',
  state_code: '',
  is_default: false,
}

const EMPTY_CODE = {
  code: '',
  description: '',
  tax_type: 'taxable',
  cgst_rate: '9',
  sgst_rate: '9',
  igst_rate: '18',
  can_claim_itc: true,
  output_cgst_account_id: '',
  output_sgst_account_id: '',
  output_igst_account_id: '',
  input_cgst_account_id: '',
  input_sgst_account_id: '',
  input_igst_account_id: '',
}

const COMPONENTS = [
  ['cgst', 'CGST'],
  ['sgst', 'SGST'],
  ['igst', 'IGST'],
]

export default function GSTPage() {
  const can = useAuth((state) => state.can)
  const [registrations, setRegistrations] = useState([])
  const [taxCodes, setTaxCodes] = useState([])
  const [accounts, setAccounts] = useState([])
  const [registrationForm, setRegistrationForm] = useState(EMPTY_REGISTRATION)
  const [codeForm, setCodeForm] = useState(EMPTY_CODE)
  const [loading, setLoading] = useState(true)
  const [savingRegistration, setSavingRegistration] = useState(false)
  const [savingCode, setSavingCode] = useState(false)
  const [pageError, setPageError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setPageError('')
    try {
      const [registrationResponse, codeResponse, accountResponse] = await Promise.all([
        api.get('/finance/tax/registrations', { params: { size: 200 } }),
        api.get('/finance/tax/codes', { params: { size: 200 } }),
        can('finance.account.read')
          ? api.get('/finance/accounts', { params: { size: 200 } })
          : Promise.resolve({ data: { items: [] } }),
      ])
      setRegistrations(registrationResponse.data.items ?? [])
      setTaxCodes(codeResponse.data.items ?? [])
      setAccounts((accountResponse.data.items ?? []).filter((account) => account.is_active))
    } catch (error) {
      setPageError(apiErrorMessage(error, 'Could not load GST configuration.'))
    } finally {
      setLoading(false)
    }
  }, [can])

  useEffect(() => { load() }, [load])

  const saveRegistration = async (event) => {
    event.preventDefault()
    setSavingRegistration(true)
    try {
      const payload = {
        ...registrationForm,
        legal_name: registrationForm.legal_name.trim(),
        gstin: registrationForm.gstin.trim().toUpperCase(),
        state_code: registrationForm.state_code.trim(),
      }
      await api.post('/finance/tax/registrations', payload)
      toast.success('GST registration added', `${payload.gstin} is ready for tax assignment.`)
      setRegistrationForm(EMPTY_REGISTRATION)
      await load()
    } catch (error) {
      toast.error('Could not save GST registration', apiErrorMessage(error))
    } finally {
      setSavingRegistration(false)
    }
  }

  const saveTaxCode = async (event) => {
    event.preventDefault()
    setSavingCode(true)
    try {
      const payload = {
        ...codeForm,
        code: codeForm.code.trim().toUpperCase(),
        description: codeForm.description.trim(),
        cgst_rate: codeForm.tax_type === 'taxable' ? codeForm.cgst_rate : '0',
        sgst_rate: codeForm.tax_type === 'taxable' ? codeForm.sgst_rate : '0',
        igst_rate: codeForm.tax_type === 'taxable' ? codeForm.igst_rate : '0',
      }
      COMPONENTS.forEach(([component]) => {
        const rate = Number(payload[`${component}_rate`])
        const outputField = `output_${component}_account_id`
        const inputField = `input_${component}_account_id`
        payload[outputField] = rate ? payload[outputField] || null : null
        payload[inputField] = rate && payload.can_claim_itc ? payload[inputField] || null : null
      })
      await api.post('/finance/tax/codes', payload)
      toast.success('GST tax code added', `${payload.code} is ready for invoice lines.`)
      setCodeForm(EMPTY_CODE)
      await load()
    } catch (error) {
      toast.error('Could not save GST tax code', apiErrorMessage(error))
    } finally {
      setSavingCode(false)
    }
  }

  const changeRegistration = async (registration, changes, message) => {
    try {
      await api.patch(`/finance/tax/registrations/${registration.id}`, changes)
      toast.success(message)
      await load()
    } catch (error) {
      toast.error('Could not update registration', apiErrorMessage(error))
    }
  }

  const deactivateCode = async (taxCode) => {
    try {
      await api.patch(`/finance/tax/codes/${taxCode.id}`, { is_active: false })
      toast.success('GST tax code deactivated', `${taxCode.code} is no longer available for new invoice lines.`)
      await load()
    } catch (error) {
      toast.error('Could not deactivate tax code', apiErrorMessage(error))
    }
  }

  const accountOptions = (accountType) => accounts
    .filter((account) => account.account_type === accountType)
    .map((account) => <option key={account.id} value={account.id}>{account.code} · {account.name}</option>)

  return (
    <>
      <PageHeader
        eyebrow="Finance · Tax controls"
        title="GST configuration"
        description="Maintain GST registrations and tax codes. Invoice line tax amounts and ledger account mappings are snapshotted for audit."
        actions={<button type="button" className="btn-secondary" onClick={load} disabled={loading}><RefreshCw size={15} /> Refresh</button>}
      />

      <div className="mb-5 flex items-start gap-3 rounded-2xl border border-primary/20 bg-primary-soft/50 p-4 text-sm text-ink-soft">
        <ShieldCheck className="mt-0.5 shrink-0 text-primary" size={18} />
        <p>Once a GST registration is active, new sales and vendor invoices must carry classified tax lines before ledger posting. Filing, e-invoicing and statutory return submission are not part of this configuration step.</p>
      </div>

      {pageError ? (
        <div className="card flex items-start gap-3 p-5 text-sm text-rose-700">
          <CircleAlert size={18} /> <span>{pageError}</span>
        </div>
      ) : loading ? (
        <div className="card flex min-h-48 items-center justify-center gap-3 text-sm text-muted"><Spinner /> Loading GST configuration…</div>
      ) : (
        <div className="grid gap-5">
          <div className="grid gap-5 xl:grid-cols-2">
            <SectionCard title="GST registrations" description="A tenant can maintain registrations across multiple states. GSTIN state prefix must match the registration state.">
              <div className="divide-y divide-line">
                {registrations.map((registration) => (
                  <div key={registration.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                    <div>
                      <p className="font-semibold text-ink">{registration.legal_name}</p>
                      <p className="mt-1 text-xs text-muted">{registration.gstin} · State {registration.state_code}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      {registration.is_default && <span className="badge bg-primary-soft text-primary">Default</span>}
                      {!registration.is_default && can('finance.taxregistration.update') && (
                        <button type="button" className="btn-ghost !px-3 !py-2" onClick={() => changeRegistration(registration, { is_default: true }, 'Default GST registration updated.')}>Make default</button>
                      )}
                      {can('finance.taxregistration.update') && (
                        <button type="button" className="btn-ghost !px-3 !py-2 text-rose-700" onClick={() => changeRegistration(registration, { is_active: false, is_default: false }, 'GST registration deactivated.')}>Deactivate</button>
                      )}
                    </div>
                  </div>
                ))}
                {!registrations.length && <p className="px-5 py-8 text-sm text-muted">No GST registrations configured.</p>}
              </div>
              {can('finance.taxregistration.create') && (
                <form onSubmit={saveRegistration} className="grid gap-3 border-t border-line bg-surface-2/50 p-5 sm:grid-cols-2">
                  <label className="form-label sm:col-span-2">Legal name<input className="input mt-1.5" maxLength={200} required value={registrationForm.legal_name} onChange={(event) => setRegistrationForm({ ...registrationForm, legal_name: event.target.value })} /></label>
                  <label className="form-label">GSTIN<input className="input mt-1.5 uppercase" maxLength={15} required value={registrationForm.gstin} onChange={(event) => setRegistrationForm({ ...registrationForm, gstin: event.target.value.toUpperCase() })} /></label>
                  <label className="form-label">State code<input className="input mt-1.5" inputMode="numeric" pattern="[0-9]{2}" maxLength={2} required value={registrationForm.state_code} onChange={(event) => setRegistrationForm({ ...registrationForm, state_code: event.target.value })} /></label>
                  <label className="flex items-center gap-2 text-xs font-semibold text-ink-soft sm:col-span-2"><input type="checkbox" checked={registrationForm.is_default} onChange={(event) => setRegistrationForm({ ...registrationForm, is_default: event.target.checked })} /> Set as default registration</label>
                  <button type="submit" className="btn-primary sm:col-span-2 sm:justify-self-start" disabled={savingRegistration}><Plus size={15} /> {savingRegistration ? 'Saving…' : 'Add registration'}</button>
                </form>
              )}
            </SectionCard>

            <SectionCard title="Tax codes" description="Configure GST components and their output-liability and recoverable input-tax GL accounts.">
              <div className="divide-y divide-line">
                {taxCodes.map((taxCode) => (
                  <div key={taxCode.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                    <div>
                      <p className="font-semibold text-ink">{taxCode.code} · {taxCode.description}</p>
                      <p className="mt-1 text-xs text-muted">{taxCode.tax_type.replace('_', ' ')} · CGST {taxCode.cgst_rate}% + SGST {taxCode.sgst_rate}% / IGST {taxCode.igst_rate}%</p>
                    </div>
                    {taxCode.can_claim_itc && <span className="badge bg-primary-soft text-primary">ITC enabled</span>}
                    {!taxCode.can_claim_itc && <span className="badge bg-surface-2 text-muted">ITC blocked</span>}
                    {can('finance.taxcode.update') && <button type="button" className="btn-ghost !px-3 !py-2 text-rose-700" onClick={() => deactivateCode(taxCode)}>Deactivate</button>}
                  </div>
                ))}
                {!taxCodes.length && <p className="px-5 py-8 text-sm text-muted">No GST tax codes configured.</p>}
              </div>
              {can('finance.taxcode.create') && (
                <form onSubmit={saveTaxCode} className="grid gap-3 border-t border-line bg-surface-2/50 p-5 sm:grid-cols-2">
                  <label className="form-label">Code<input className="input mt-1.5 uppercase" maxLength={30} required value={codeForm.code} onChange={(event) => setCodeForm({ ...codeForm, code: event.target.value.toUpperCase() })} /></label>
                  <label className="form-label">Tax treatment<select className="input mt-1.5" value={codeForm.tax_type} onChange={(event) => setCodeForm({ ...codeForm, tax_type: event.target.value })}><option value="taxable">Taxable</option><option value="exempt">Exempt</option><option value="zero_rated">Zero-rated</option><option value="non_gst">Non-GST</option></select></label>
                  <label className="form-label sm:col-span-2">Description<input className="input mt-1.5" maxLength={200} required value={codeForm.description} onChange={(event) => setCodeForm({ ...codeForm, description: event.target.value })} /></label>
                  {codeForm.tax_type === 'taxable' && COMPONENTS.map(([component, label]) => (
                    <label className="form-label" key={`${component}-rate`}>{label} rate %<input className="input mt-1.5" type="number" min="0" max="100" step="0.01" value={codeForm[`${component}_rate`]} onChange={(event) => setCodeForm({ ...codeForm, [`${component}_rate`]: event.target.value })} /></label>
                  ))}
                  {codeForm.tax_type === 'taxable' && COMPONENTS.map(([component, label]) => {
                    const rate = Number(codeForm[`${component}_rate`] || 0)
                    if (!rate) return null
                    return (
                      <div className="grid gap-3 sm:col-span-2 sm:grid-cols-2" key={`${component}-accounts`}>
                        <label className="form-label">Output {label} liability
                          <select className="input mt-1.5" required value={codeForm[`output_${component}_account_id`]} onChange={(event) => setCodeForm({ ...codeForm, [`output_${component}_account_id`]: event.target.value })}>
                            <option value="">Select liability account</option>{accountOptions('liability')}
                          </select>
                        </label>
                        {codeForm.can_claim_itc && <label className="form-label">Input {label} recoverable asset
                          <select className="input mt-1.5" required value={codeForm[`input_${component}_account_id`]} onChange={(event) => setCodeForm({ ...codeForm, [`input_${component}_account_id`]: event.target.value })}>
                            <option value="">Select asset account</option>{accountOptions('asset')}
                          </select>
                        </label>}
                      </div>
                    )
                  })}
                  <label className="flex items-center gap-2 text-xs font-semibold text-ink-soft sm:col-span-2"><input type="checkbox" checked={codeForm.can_claim_itc} onChange={(event) => setCodeForm({ ...codeForm, can_claim_itc: event.target.checked })} /> Input GST is eligible for ITC</label>
                  {!accounts.length && <p className="text-xs text-rose-700 sm:col-span-2">Active GL accounts could not be loaded. Configure account access and the chart of accounts before adding tax codes.</p>}
                  <button type="submit" className="btn-primary sm:col-span-2 sm:justify-self-start" disabled={savingCode}><Plus size={15} /> {savingCode ? 'Saving…' : 'Add tax code'}</button>
                </form>
              )}
            </SectionCard>
          </div>

          <SectionCard title="Posting controls" description="GST amounts are calculated from line-level taxable values and saved with the invoice.">
            <div className="grid gap-3 p-5 text-sm text-ink-soft md:grid-cols-3">
              <Control icon={BadgeCheck} title="Intra-state supplies" detail="CGST and SGST are calculated separately using the registration state and place of supply." />
              <Control icon={BadgeCheck} title="Inter-state supplies" detail="IGST is applied when the place-of-supply state differs from the selected GST registration." />
              <Control icon={BadgeCheck} title="Posting snapshots" detail="Sales GST credits output-liability accounts; eligible vendor ITC debits input-tax asset accounts." />
            </div>
          </SectionCard>
        </div>
      )}
    </>
  )
}

function Control({ icon: Icon, title, detail }) {
  return (
    <div className="rounded-xl border border-line bg-surface-2/50 p-4">
      <p className="flex items-center gap-2 font-semibold text-ink"><Icon size={15} className="text-primary" /> {title}</p>
      <p className="mt-2 text-xs leading-relaxed text-muted">{detail}</p>
    </div>
  )
}
