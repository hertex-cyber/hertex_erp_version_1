import { useCallback, useEffect, useState } from 'react'
import { Receipt, RefreshCw, ShieldCheck, Trash2, Upload } from 'lucide-react'
import { DataTable } from '../../components/DataTable'
import { RemoteSelect } from '../../components/Form'
import {
  Badge,
  EmptyState,
  Modal,
  PageHeader,
  Pagination,
  SearchInput,
  SectionCard,
} from '../../components/ui'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel, dateTimeLabel, money, pct, titleCase } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

const PAGE_SIZE = 20

function confirmInitialValues(draft) {
  return {
    vendor_id: draft.vendor_id ?? '',
    purchase_order_id: '',
    invoice_number: draft.invoice_number ?? '',
    issue_date: draft.invoice_date ?? '',
    amount: draft.amount ?? '',
    tax_amount: draft.tax_amount ?? '',
    gstin: draft.gstin ?? '',
    due_date: '',
    notes: '',
  }
}

export default function OcrInboxPage() {
  const can = useAuth((state) => state.can)
  const canRead = can('procurement.vendorinvoice.read')
  const canCreate = can('procurement.vendorinvoice.create')
  const canReview = can('procurement.vendorinvoice.update')
  const canDelete = can('procurement.vendorinvoice.delete')
  const [mode, setMode] = useState('text')
  const [provider, setProvider] = useState('auto')
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [fileKey, setFileKey] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [detail, setDetail] = useState(null)
  const [confirmTarget, setConfirmTarget] = useState(null)
  const [confirmForm, setConfirmForm] = useState({})
  const [rejectTarget, setRejectTarget] = useState(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      const { data } = await api.get('/procurement/ocr/drafts', {
        params: {
          page,
          size: PAGE_SIZE,
          ...(status ? { status } : {}),
          ...(q.trim() ? { q: q.trim() } : {}),
        },
      })
      setRows(data.items ?? [])
      setTotal(data.total ?? 0)
      setPages(data.pages ?? Math.max(1, Math.ceil((data.total ?? 0) / PAGE_SIZE)))
    } catch (requestError) {
      setLoadError(apiErrorMessage(requestError, 'Could not load OCR drafts.'))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [page, status, q])

  useEffect(() => {
    if (canRead) load()
  }, [canRead, load])

  const submitDocument = async (event) => {
    event.preventDefault()
    if (!canCreate) return
    setFormError('')
    if (mode === 'text' && !text.trim()) {
      setFormError('Paste invoice text or a JSON document before extracting.')
      return
    }
    if (mode === 'file' && !file) {
      setFormError('Choose an invoice file to upload.')
      return
    }
    setSubmitting(true)
    try {
      if (mode === 'file') {
        const body = new FormData()
        body.append('file', file)
        body.append('provider', provider)
        const { data } = await api.post('/procurement/ocr/documents/upload', body)
        toast.success('Document ingested', `${data.vendor_name} · ${data.invoice_number}`)
      } else {
        const { data } = await api.post('/procurement/ocr/documents', {
          text: text.trim(),
          provider,
        })
        toast.success('Draft extracted', `${data.vendor_name} · ${data.invoice_number}`)
      }
      setText('')
      setFile(null)
      setFileKey((current) => current + 1)
      setPage(1)
      await load()
    } catch (requestError) {
      setFormError(apiErrorMessage(requestError))
    } finally {
      setSubmitting(false)
    }
  }

  const openDetail = async (draft) => {
    try {
      const { data } = await api.get(`/procurement/ocr/drafts/${draft.id}`)
      setDetail(data)
    } catch (requestError) {
      toast.error('Could not load OCR draft', apiErrorMessage(requestError))
    }
  }

  const openConfirm = (draft) => {
    setConfirmTarget(draft)
    setConfirmForm(confirmInitialValues(draft))
    setFormError('')
  }

  const confirmDraft = async (event) => {
    event.preventDefault()
    if (!confirmTarget || !confirmForm.vendor_id) {
      setFormError('Select a vendor before confirming this OCR draft.')
      return
    }
    setBusy(true)
    setFormError('')
    try {
      const payload = {
        vendor_id: confirmForm.vendor_id,
        purchase_order_id: confirmForm.purchase_order_id || null,
        invoice_number: confirmForm.invoice_number || null,
        issue_date: confirmForm.issue_date || null,
        amount: confirmForm.amount === '' ? null : confirmForm.amount,
        tax_amount: confirmForm.tax_amount === '' ? null : confirmForm.tax_amount,
        gstin: confirmForm.gstin || null,
        due_date: confirmForm.due_date || null,
        notes: confirmForm.notes || null,
      }
      const { data } = await api.post(
        `/procurement/ocr/drafts/${confirmTarget.id}/confirm`,
        payload,
      )
      toast.success('Vendor invoice created', `${data.invoice_number} saved as a draft.`)
      setConfirmTarget(null)
      setDetail(null)
      await load()
    } catch (requestError) {
      setFormError(apiErrorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  const openReject = (draft) => {
    setRejectTarget(draft)
    setReason('')
    setFormError('')
  }

  const rejectDraft = async (event) => {
    event.preventDefault()
    if (!rejectTarget || !reason.trim()) {
      setFormError('Enter a rejection reason.')
      return
    }
    setBusy(true)
    setFormError('')
    try {
      const { data } = await api.post(
        `/procurement/ocr/drafts/${rejectTarget.id}/reject`,
        { reason: reason.trim() },
      )
      toast.success('Draft rejected', `${data.invoice_number} · ${reason.trim()}`)
      setRejectTarget(null)
      setDetail(null)
      await load()
    } catch (requestError) {
      setFormError(apiErrorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  const deleteDraft = async (draft) => {
    setBusy(true)
    try {
      await api.delete(`/procurement/ocr/drafts/${draft.id}`)
      toast.success('OCR draft deleted', draft.invoice_number)
      setDetail(null)
      await load()
    } catch (requestError) {
      toast.error('Could not delete OCR draft', apiErrorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  const updateConfirmForm = (field, value) => {
    setConfirmForm((current) => ({ ...current, [field]: value }))
  }

  if (!canRead) {
    return (
      <>
        <PageHeader
          eyebrow="Procurement · OCR ingestion"
          title="OCR inbox"
          description="Extract vendor invoice fields from pasted text or an uploaded document."
        />
        <EmptyState
          icon={Receipt}
          title="No OCR access"
          description="Ask an administrator for vendor invoice read access."
        />
      </>
    )
  }

  return (
    <>
      <PageHeader
        eyebrow="Procurement · OCR ingestion"
        title="OCR inbox"
        description="Ingest invoice documents, review extracted fields with confidence scores, and promote accepted drafts to vendor invoices."
        actions={
          <button type="button" className="btn-secondary" onClick={load} disabled={loading}>
            <RefreshCw size={15} /> Refresh
          </button>
        }
      />

      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.4fr)]">
        <div className="grid gap-5">
          <SectionCard
            title="Submit an invoice"
            description="Local extraction reads plain text or JSON; external extraction uses the configured OCR credential."
          >
            <form onSubmit={submitDocument} className="grid gap-4 p-5">
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className={`rounded-xl px-3.5 py-2 text-xs font-bold transition ${
                    mode === 'text'
                      ? 'bg-primary text-white shadow-sm'
                      : 'border border-line bg-surface text-ink-soft hover:bg-surface-2'
                  }`}
                  onClick={() => setMode('text')}
                >
                  Paste text
                </button>
                <button
                  type="button"
                  className={`rounded-xl px-3.5 py-2 text-xs font-bold transition ${
                    mode === 'file'
                      ? 'bg-primary text-white shadow-sm'
                      : 'border border-line bg-surface text-ink-soft hover:bg-surface-2'
                  }`}
                  onClick={() => setMode('file')}
                >
                  Upload file
                </button>
              </div>
              <label className="form-label">
                Extraction provider
                <select
                  className="input mt-1.5"
                  value={provider}
                  onChange={(event) => setProvider(event.target.value)}
                >
                  <option value="auto">Auto</option>
                  <option value="local">Local extraction</option>
                  <option value="external">External OCR credential</option>
                </select>
              </label>
              {mode === 'text' ? (
                <label className="form-label">
                  Invoice text or JSON document
                  <textarea
                    className="input mt-1.5 min-h-[180px] resize-y font-mono text-xs"
                    value={text}
                    placeholder={'Vendor: Acme Supplies\nInvoice No: INV-2026-001\nDate: 2026-11-20\nGSTIN: 27AAPFU0939F1ZV\nTotal: 1250.00\nGST: 225.00'}
                    onChange={(event) => setText(event.target.value)}
                  />
                </label>
              ) : (
                <label className="form-label">
                  Invoice file
                  <input
                    key={fileKey}
                    className="input mt-1.5"
                    type="file"
                    accept=".txt,.json,.csv,.pdf,.png,.jpg,.jpeg"
                    onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  />
                </label>
              )}
              {formError && <p className="text-xs font-semibold text-rose-600">{formError}</p>}
              {canCreate ? (
                <button type="submit" className="btn-primary justify-self-start" disabled={submitting}>
                  <Upload size={15} /> {submitting ? 'Extracting…' : 'Extract invoice'}
                </button>
              ) : (
                <p className="text-xs text-muted">
                  You can review drafts, but invoice creation permission is required to ingest documents.
                </p>
              )}
            </form>
          </SectionCard>
          <SectionCard title="Review policy" description="Extraction never posts to the ledger.">
            <div className="grid gap-3 p-5 text-xs leading-relaxed text-ink-soft">
              <p className="flex items-start gap-2">
                <ShieldCheck size={15} className="mt-0.5 shrink-0 text-primary" />
                Every draft keeps its source digest, provider and confidence score for review.
              </p>
              <p className="flex items-start gap-2">
                <Receipt size={15} className="mt-0.5 shrink-0 text-primary" />
                Confirming requires a vendor and creates a draft vendor invoice only.
              </p>
              <p className="flex items-start gap-2">
                <Trash2 size={15} className="mt-0.5 shrink-0 text-primary" />
                Rejected drafts keep their reason; confirmed drafts cannot be deleted.
              </p>
            </div>
          </SectionCard>
        </div>

        <SectionCard
          title="Extracted drafts"
          description={`${total} drafts match the current filters.`}
        >
          <div className="flex flex-wrap gap-3 border-b border-line p-4">
            <SearchInput
              value={q}
              onChange={(value) => {
                setQ(value)
                setPage(1)
              }}
              placeholder="Search vendor, invoice or GSTIN…"
              className="min-w-[220px] flex-1"
            />
            <select
              className="input w-auto min-w-[150px]"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value)
                setPage(1)
              }}
            >
              <option value="">All statuses</option>
              <option value="pending">Pending</option>
              <option value="confirmed">Confirmed</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
          {loadError ? (
            <div className="p-5 text-sm text-rose-700">{loadError}</div>
          ) : (
            <DataTable
              columns={[
                {
                  key: 'vendor_name',
                  label: 'Vendor',
                  render: (row) => (
                    <div>
                      <p className="font-semibold text-ink">{row.vendor_name}</p>
                      <p className="text-[11px] text-muted">{row.gstin || 'No GSTIN'}</p>
                    </div>
                  ),
                },
                { key: 'invoice_number', label: 'Invoice' },
                { key: 'invoice_date', label: 'Date', render: (row) => dateLabel(row.invoice_date) },
                {
                  key: 'amount',
                  label: 'Amount',
                  align: 'right',
                  render: (row) => money(row.amount, { precise: true }),
                },
                {
                  key: 'tax_amount',
                  label: 'Tax',
                  align: 'right',
                  render: (row) => money(row.tax_amount, { precise: true }),
                },
                {
                  key: 'confidence',
                  label: 'Confidence',
                  align: 'right',
                  render: (row) => pct(Number(row.confidence) * 100, 1),
                },
                { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
                {
                  key: 'provider',
                  label: 'Provider',
                  render: (row) => <Badge>{row.provider}</Badge>,
                },
                {
                  key: 'created_at',
                  label: 'Received',
                  render: (row) => dateTimeLabel(row.created_at),
                },
              ]}
              rows={rows}
              loading={loading}
              onRowClick={openDetail}
              empty={
                <EmptyState
                  icon={Receipt}
                  title="No OCR drafts"
                  description="Submit an invoice document to create the first review draft."
                  compact
                />
              }
              rowActions={(row) => (
                <>
                  {canReview && row.status === 'pending' && (
                    <button
                      type="button"
                      className="btn-secondary py-1 text-xs"
                      onClick={() => openConfirm(row)}
                    >
                      Confirm
                    </button>
                  )}
                  {canReview && row.status === 'pending' && (
                    <button
                      type="button"
                      className="btn-secondary py-1 text-xs"
                      onClick={() => openReject(row)}
                    >
                      Reject
                    </button>
                  )}
                  {canDelete && row.status !== 'confirmed' && (
                    <button
                      type="button"
                      className="btn-ghost py-1 text-xs text-rose-700"
                      onClick={() => deleteDraft(row)}
                      disabled={busy}
                      aria-label="Delete draft"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </>
              )}
            />
          )}
          <Pagination page={page} pages={pages} total={total} size={PAGE_SIZE} onPage={setPage} />
        </SectionCard>
      </div>

      <Modal
        open={Boolean(detail)}
        onClose={() => setDetail(null)}
        title={detail?.invoice_number ?? 'OCR draft'}
        description={detail ? `${detail.vendor_name} · ${detail.provider}` : ''}
        size="lg"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setDetail(null)}>
              Close
            </button>
            {detail?.status === 'pending' && canReview && (
              <>
                <button type="button" className="btn-secondary" onClick={() => openReject(detail)}>
                  Reject
                </button>
                <button type="button" className="btn-primary" onClick={() => openConfirm(detail)}>
                  Confirm
                </button>
              </>
            )}
            {detail && canDelete && detail.status !== 'confirmed' && (
              <button
                type="button"
                className="btn-secondary text-rose-700"
                onClick={() => deleteDraft(detail)}
                disabled={busy}
              >
                Delete
              </button>
            )}
          </>
        }
      >
        {detail && (
          <div className="grid gap-4">
            <div className="grid gap-3 sm:grid-cols-3">
              {[
                ['Confidence', pct(Number(detail.confidence) * 100, 1)],
                ['Status', titleCase(detail.status)],
                ['Source', titleCase(detail.source_type)],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-line bg-surface-2/50 p-4">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-muted">{label}</p>
                  <p className="mt-1 font-semibold text-ink">{value}</p>
                </div>
              ))}
            </div>
            <div className="grid gap-2 text-xs text-muted sm:grid-cols-2">
              <span>Vendor: <span className="font-semibold text-ink">{detail.vendor_name}</span></span>
              <span>GSTIN: <span className="font-semibold text-ink">{detail.gstin || '—'}</span></span>
              <span>Invoice date: <span className="font-semibold text-ink">{dateLabel(detail.invoice_date)}</span></span>
              <span>Amount: <span className="font-semibold text-ink">{money(detail.amount, { precise: true })}</span></span>
              <span>Tax: <span className="font-semibold text-ink">{money(detail.tax_amount, { precise: true })}</span></span>
              <span>Provider: <span className="font-semibold text-ink">{detail.provider}</span></span>
              <span>Received: <span className="font-semibold text-ink">{dateTimeLabel(detail.created_at)}</span></span>
              <span>Filename: <span className="font-semibold text-ink">{detail.filename || '—'}</span></span>
            </div>
            {detail.rejection_reason && (
              <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-700">
                Rejection reason: {detail.rejection_reason}
              </div>
            )}
            {detail.confirmed_invoice_id && (
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-700">
                Vendor invoice: <span className="font-mono">{detail.confirmed_invoice_id}</span>
              </div>
            )}
          </div>
        )}
      </Modal>

      <Modal
        open={Boolean(confirmTarget)}
        onClose={() => !busy && setConfirmTarget(null)}
        title="Confirm OCR draft"
        description={
          confirmTarget
            ? `${confirmTarget.vendor_name} · ${confirmTarget.invoice_number}`
            : ''
        }
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setConfirmTarget(null)} disabled={busy}>
              Cancel
            </button>
            <button
              type="submit"
              form="ocr-confirm-form"
              className="btn-primary"
              disabled={busy || !confirmForm.vendor_id}
            >
              {busy ? 'Confirming…' : 'Create vendor invoice'}
            </button>
          </>
        }
      >
        <form id="ocr-confirm-form" onSubmit={confirmDraft} className="grid gap-4 sm:grid-cols-2">
          <label className="form-label sm:col-span-2">
            Vendor <span className="ml-1 text-accent">*</span>
            <RemoteSelect
              lookup="vendors"
              value={confirmForm.vendor_id}
              onChange={(value) => updateConfirmForm('vendor_id', value)}
              placeholder="Select a vendor"
            />
          </label>
          <label className="form-label sm:col-span-2">
            Purchase order (optional)
            <RemoteSelect
              lookup="purchaseOrders"
              value={confirmForm.purchase_order_id}
              onChange={(value) => updateConfirmForm('purchase_order_id', value)}
              placeholder="No purchase order"
            />
          </label>
          <label className="form-label">
            Invoice number
            <input
              className="input mt-1.5"
              value={confirmForm.invoice_number ?? ''}
              onChange={(event) => updateConfirmForm('invoice_number', event.target.value)}
            />
          </label>
          <label className="form-label">
            Issue date
            <input
              className="input mt-1.5"
              type="date"
              value={confirmForm.issue_date ?? ''}
              onChange={(event) => updateConfirmForm('issue_date', event.target.value)}
            />
          </label>
          <label className="form-label">
            Amount
            <input
              className="input mt-1.5"
              type="number"
              min={0}
              step="0.01"
              value={confirmForm.amount ?? ''}
              onChange={(event) => updateConfirmForm('amount', event.target.value)}
            />
          </label>
          <label className="form-label">
            Tax amount
            <input
              className="input mt-1.5"
              type="number"
              min={0}
              step="0.01"
              value={confirmForm.tax_amount ?? ''}
              onChange={(event) => updateConfirmForm('tax_amount', event.target.value)}
            />
          </label>
          <label className="form-label">
            GSTIN
            <input
              className="input mt-1.5"
              value={confirmForm.gstin ?? ''}
              onChange={(event) => updateConfirmForm('gstin', event.target.value)}
            />
          </label>
          <label className="form-label">
            Due date
            <input
              className="input mt-1.5"
              type="date"
              value={confirmForm.due_date ?? ''}
              onChange={(event) => updateConfirmForm('due_date', event.target.value)}
            />
          </label>
          <label className="form-label sm:col-span-2">
            Notes
            <textarea
              className="input mt-1.5 min-h-[80px] resize-y"
              value={confirmForm.notes ?? ''}
              onChange={(event) => updateConfirmForm('notes', event.target.value)}
            />
          </label>
          {!confirmForm.vendor_id && (
            <p className="text-xs font-semibold text-rose-600 sm:col-span-2">
              Select a vendor before confirming this OCR draft.
            </p>
          )}
          {formError && <p className="text-xs font-semibold text-rose-600 sm:col-span-2">{formError}</p>}
        </form>
      </Modal>

      <Modal
        open={Boolean(rejectTarget)}
        onClose={() => !busy && setRejectTarget(null)}
        title="Reject OCR draft"
        description={rejectTarget ? `${rejectTarget.vendor_name} · ${rejectTarget.invoice_number}` : ''}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setRejectTarget(null)} disabled={busy}>
              Cancel
            </button>
            <button
              type="submit"
              form="ocr-reject-form"
              className="btn-primary"
              disabled={busy || !reason.trim()}
            >
              {busy ? 'Rejecting…' : 'Reject draft'}
            </button>
          </>
        }
      >
        <form id="ocr-reject-form" onSubmit={rejectDraft} className="grid gap-4">
          <label className="form-label">
            Rejection reason <span className="ml-1 text-accent">*</span>
            <textarea
              className="input mt-1.5 min-h-[100px] resize-y"
              maxLength={500}
              required
              value={reason}
              placeholder="Explain why this extraction cannot be confirmed"
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          {formError && <p className="text-xs font-semibold text-rose-600">{formError}</p>}
        </form>
      </Modal>
    </>
  )
}
