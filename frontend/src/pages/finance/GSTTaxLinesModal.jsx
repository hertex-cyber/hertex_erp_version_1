import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { Modal } from '../../components/ui'
import { api, apiErrorMessage } from '../../lib/api'
import { toast } from '../../store/toast'

export default function GSTTaxLinesModal({
  invoice,
  open,
  invoiceType,
  onClose,
  onSaved,
}) {
  const [taxCodes, setTaxCodes] = useState([])
  const [registrations, setRegistrations] = useState([])
  const [lines, setLines] = useState([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open || !invoice) return
    let active = true
    setLoading(true)
    Promise.all([
      api.get('/finance/tax/codes', { params: { size: 200 } }),
      api.get('/finance/tax/registrations', { params: { size: 200 } }),
    ]).then(([codesResponse, registrationsResponse]) => {
      if (!active) return
      const codes = codesResponse.data.items ?? []
      const registrationsList = registrationsResponse.data.items ?? []
      setTaxCodes(codes)
      setRegistrations(registrationsList)
      setLines(invoice.tax_lines?.length
        ? invoice.tax_lines.map((line) => ({
          tax_code_id: line.tax_code_id,
          registration_id: line.registration_id,
          place_of_supply_state_code: line.place_of_supply_state_code,
          taxable_amount: String(line.taxable_amount),
          description: line.description ?? '',
        }))
        : [{
          tax_code_id: codes[0]?.id ?? '',
          registration_id: registrationsList.find((item) => item.is_default)?.id ?? registrationsList[0]?.id ?? '',
          place_of_supply_state_code: '',
          taxable_amount: String(invoice.amount ?? invoice.subtotal ?? ''),
          description: '',
        }])
    }).catch((error) => {
      if (active) toast.error('Could not load GST tax options', apiErrorMessage(error))
    }).finally(() => active && setLoading(false))
    return () => { active = false }
  }, [invoice, open])

  const updateLine = (index, field, value) => {
    setLines((current) => current.map((line, lineIndex) => (
      lineIndex === index ? { ...line, [field]: value } : line
    )))
  }

  const submit = async (event) => {
    event.preventDefault()
    if (!invoice || !lines.length) return
    setSaving(true)
    try {
      const endpoint = invoiceType === 'vendor'
        ? `/procurement/vendor-invoices/${invoice.id}/tax-lines`
        : `/finance/invoices/${invoice.id}/tax-lines`
      await api.put(endpoint, {
        lines: lines.map((line) => ({
          ...line,
          description: line.description.trim() || null,
        })),
      })
      toast.success('GST lines saved', `${invoice.invoice_number} tax was calculated from its taxable lines.`)
      onClose()
      await onSaved?.()
    } catch (error) {
      toast.error('Could not save GST lines', apiErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  const appendLine = () => setLines((current) => [
    ...current,
    {
      tax_code_id: taxCodes[0]?.id ?? '',
      registration_id: registrations.find((item) => item.is_default)?.id ?? registrations[0]?.id ?? '',
      place_of_supply_state_code: '',
      taxable_amount: '0',
      description: '',
    },
  ])

  return (
    <Modal
      open={open}
      onClose={() => !saving && onClose()}
      title={invoiceType === 'vendor' ? 'Vendor invoice GST lines' : 'Customer invoice GST lines'}
      description={invoice ? `${invoice.invoice_number} · taxable base ${invoice.amount ?? invoice.subtotal}` : ''}
      size="xl"
      footer={(
        <>
          <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="submit" form="invoice-gst-lines-form" className="btn-primary" disabled={saving || loading || !lines.length}>{saving ? 'Saving…' : 'Calculate and save GST'}</button>
        </>
      )}
    >
      <form id="invoice-gst-lines-form" onSubmit={submit} className="grid gap-4">
        <p className="text-xs leading-relaxed text-muted">Each line stores a tax code, GST registration and place-of-supply snapshot. Taxable values are validated against the invoice base; GST is calculated by the server.</p>
        {loading && <p className="text-sm text-muted">Loading tax codes and registrations…</p>}
        {!loading && (!taxCodes.length || !registrations.length) && <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">Create an active GST registration and at least one tax code before adding invoice lines.</p>}
        {lines.map((line, index) => (
          <div key={`${invoice?.id}-gst-${index}`} className="grid gap-3 rounded-xl border border-line p-4 sm:grid-cols-2 lg:grid-cols-4">
            <label className="form-label lg:col-span-2">Tax code
              <select className="input mt-1.5" required value={line.tax_code_id} onChange={(event) => updateLine(index, 'tax_code_id', event.target.value)}>
                <option value="">Select tax code</option>
                {taxCodes.map((code) => <option key={code.id} value={code.id}>{code.code} · {code.description}</option>)}
              </select>
            </label>
            <label className="form-label lg:col-span-2">GST registration
              <select className="input mt-1.5" required value={line.registration_id} onChange={(event) => updateLine(index, 'registration_id', event.target.value)}>
                <option value="">Select registration</option>
                {registrations.map((registration) => <option key={registration.id} value={registration.id}>{registration.gstin} · State {registration.state_code}</option>)}
              </select>
            </label>
            <label className="form-label">Place-of-supply state
              <input className="input mt-1.5" inputMode="numeric" pattern="[0-9]{2}" maxLength={2} required value={line.place_of_supply_state_code} onChange={(event) => updateLine(index, 'place_of_supply_state_code', event.target.value)} />
            </label>
            <label className="form-label">Taxable amount
              <input className="input mt-1.5" type="number" min="0" step="0.01" required value={line.taxable_amount} onChange={(event) => updateLine(index, 'taxable_amount', event.target.value)} />
            </label>
            <label className="form-label lg:col-span-2">Description
              <input className="input mt-1.5" maxLength={255} value={line.description} onChange={(event) => updateLine(index, 'description', event.target.value)} />
            </label>
            <div className="flex items-end justify-end">
              <button type="button" className="btn-ghost text-rose-700" aria-label="Remove tax line" onClick={() => setLines((current) => current.filter((_, lineIndex) => lineIndex !== index))}><Trash2 size={15} /> Remove</button>
            </div>
          </div>
        ))}
        <button type="button" className="btn-secondary justify-self-start" onClick={appendLine} disabled={loading}><Plus size={15} /> Add tax line</button>
      </form>
    </Modal>
  )
}
