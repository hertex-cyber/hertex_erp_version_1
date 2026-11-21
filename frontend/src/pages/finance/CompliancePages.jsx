import { useCallback, useEffect, useState } from 'react'
import {
  BadgeIndianRupee,
  FileText,
  RefreshCw,
  Send,
  ShieldCheck,
  Truck,
  Upload,
  Webhook,
} from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { Badge, EmptyState, Modal, PageHeader } from '../../components/ui'
import { RemoteSelect } from '../../components/Form'
import { DataTable } from '../../components/DataTable'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel, dateTimeLabel, money, today } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

function Tabs({ items, value, onChange }) {
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className={`rounded-xl px-3.5 py-2 text-xs font-bold transition ${
            value === item.key
              ? 'bg-primary text-white shadow-sm'
              : 'border border-line bg-surface text-ink-soft hover:bg-surface-2'
          }`}
          onClick={() => onChange(item.key)}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}

function Panel({ title, description, actions, children }) {
  return (
    <section className="card overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="display text-lg font-semibold text-ink">{title}</h2>
          {description && <p className="mt-1 text-xs text-muted">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  )
}

function JsonBlock({ value }) {
  return (
    <pre className="max-h-64 overflow-auto rounded-xl bg-surface-2 p-3 text-[11px] leading-relaxed text-ink-soft">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  )
}

function usePaged(endpoint, params = {}, enabled = true) {
  const serialized = JSON.stringify(params)
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    if (!enabled) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const { data } = await api.get(endpoint, { params: { size: 200, ...params } })
      setRows(data.items ?? [])
      setTotal(data.total ?? data.items?.length ?? 0)
    } catch (requestError) {
      setError(apiErrorMessage(requestError))
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [endpoint, serialized, enabled])

  useEffect(() => {
    load()
  }, [load])

  return { rows, total, loading, error, reload: load }
}

const CONTROL_TABS = [
  { key: 'audit', label: 'Audit trail', permission: 'finance.financeaudit.read' },
  { key: 'source', label: 'Source events', permission: 'finance.sourceevent.read' },
  { key: 'outbox', label: 'Outbox', permission: 'finance.outbox.read' },
  { key: 'webhooks', label: 'Webhooks', permission: 'finance.webhook.read' },
  { key: 'deliveries', label: 'Deliveries', permission: 'finance.webhookdelivery.read' },
]

export function ControlPlanePage() {
  const can = useAuth((state) => state.can)
  const [tab, setTab] = useState('audit')
  const [detail, setDetail] = useState(null)
  const [busy, setBusy] = useState(false)
  const audit = usePaged('/finance/control/audit', {}, can('finance.financeaudit.read'))
  const sources = usePaged('/finance/control/source-events', {}, can('finance.sourceevent.read'))
  const outbox = usePaged('/finance/control/outbox', {}, can('finance.outbox.read'))
  const deliveries = usePaged('/finance/control/webhook-deliveries', {}, can('finance.webhookdelivery.read'))

  const dispatch = async (force = false) => {
    setBusy(true)
    try {
      const { data } = await api.post('/finance/control/outbox/dispatch', null, {
        params: { limit: 50, force },
      })
      toast.success('Outbox dispatch complete', `${data.delivered} delivered · ${data.retried} retried`)
      outbox.reload()
      deliveries.reload()
    } catch (error) {
      toast.error('Could not dispatch outbox', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const retry = async (row) => {
    setBusy(true)
    try {
      await api.post(`/finance/control/outbox/${row.id}/retry`)
      toast.success('Dead-letter event requeued', row.event_type)
      outbox.reload()
    } catch (error) {
      toast.error('Could not retry event', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const visibleTabs = CONTROL_TABS.filter((item) => can(item.permission))
  const activeTab = visibleTabs.some((item) => item.key === tab) ? tab : visibleTabs[0]?.key

  return (
    <>
      <PageHeader
        eyebrow="Finance · Controls"
        title="Financial control plane"
        description="Trace every posting, source event, webhook and dead-letter delivery from one place."
      />
      <Tabs items={visibleTabs} value={activeTab} onChange={setTab} />
      {!visibleTabs.length && (
        <EmptyState
          icon={ShieldCheck}
          title="No control access"
          description="Ask an administrator for finance audit or outbox permissions."
        />
      )}
      {activeTab === 'audit' && (
        <Panel title="Audit trail" description={`${audit.total} immutable finance audit entries`}>
          <DataTable
            columns={[
              { key: 'created_at', label: 'When', render: (row) => dateTimeLabel(row.created_at) },
              { key: 'actor_email', label: 'Actor' },
              { key: 'action', label: 'Action', render: (row) => <Badge>{row.action}</Badge> },
              { key: 'entity_type', label: 'Entity' },
              { key: 'entity_id', label: 'Record', render: (row) => <span className="font-mono text-[11px]">{row.entity_id?.slice(0, 8)}</span> },
              { key: 'reason', label: 'Reason' },
            ]}
            rows={audit.rows}
            loading={audit.loading}
            onRowClick={setDetail}
            empty={<EmptyState icon={ShieldCheck} title="No audit entries yet" description="Post a journal to see the control trail." compact />}
          />
        </Panel>
      )}
      {activeTab === 'source' && (
        <Panel title="Source events" description="Idempotency-protected inbound integrations">
          <DataTable
            columns={[
              { key: 'created_at', label: 'When', render: (row) => dateTimeLabel(row.created_at) },
              { key: 'event_type', label: 'Event' },
              { key: 'source_module', label: 'Module' },
              { key: 'idempotency_key', label: 'Idempotency key', render: (row) => <span className="font-mono text-[11px]">{row.idempotency_key}</span> },
              { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
              { key: 'attempts', label: 'Attempts', align: 'right' },
            ]}
            rows={sources.rows}
            loading={sources.loading}
            empty={<EmptyState icon={RefreshCw} title="No source events" compact />}
          />
        </Panel>
      )}
      {activeTab === 'outbox' && (
        <Panel
          title="Outbox"
          description={`${outbox.total} durable integration events`}
          actions={
            <>
              {can('finance.outbox.dispatch') && (
                <button type="button" className="btn-secondary" onClick={() => dispatch(false)} disabled={busy}>
                  <Send size={15} /> Dispatch due
                </button>
              )}
              {can('finance.outbox.dispatch') && (
                <button type="button" className="btn-secondary" onClick={() => dispatch(true)} disabled={busy}>
                  <RefreshCw size={15} /> Force dispatch
                </button>
              )}
            </>
          }
        >
          <DataTable
            columns={[
              { key: 'created_at', label: 'When', render: (row) => dateTimeLabel(row.created_at) },
              { key: 'event_type', label: 'Event' },
              { key: 'aggregate_type', label: 'Aggregate' },
              { key: 'aggregate_id', label: 'Record', render: (row) => <span className="font-mono text-[11px]">{row.aggregate_id?.slice(0, 8)}</span> },
              { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
              { key: 'attempts', label: 'Attempts', align: 'right' },
            ]}
            rows={outbox.rows}
            loading={outbox.loading}
            empty={<EmptyState icon={Send} title="Outbox is empty" compact />}
            rowActions={(row) =>
              row.status === 'dead' && can('finance.outbox.retry') ? (
                <button type="button" className="btn-secondary py-1 text-xs" onClick={() => retry(row)} disabled={busy}>
                  Retry
                </button>
              ) : null
            }
          />
        </Panel>
      )}
      {activeTab === 'webhooks' && can('finance.webhook.read') && (
        <ResourcePage
          title="Webhook endpoints"
          eyebrow="Finance · Controls"
          description="Signed HTTPS callbacks for outbox events."
          endpoint="/finance/control/webhooks"
          permission="finance.webhook"
          createLabel="Add endpoint"
          searchPlaceholder="Search endpoints…"
          columns={[
            { key: 'name', label: 'Endpoint' },
            { key: 'url', label: 'URL', render: (row) => <span className="font-mono text-[11px]">{row.url}</span> },
            { key: 'event_types', label: 'Events', render: (row) => row.event_types?.join(', ') || 'All' },
            { key: 'is_enabled', label: 'Enabled', render: (row) => <Badge>{row.is_enabled ? 'active' : 'disabled'}</Badge> },
          ]}
          fields={[
            { name: 'name', label: 'Name', required: true },
            { name: 'url', label: 'HTTPS URL', required: true },
            { name: 'secret', label: 'Signing secret', required: true, help: 'At least 16 characters.' },
            { name: 'event_types', label: 'Event types (JSON list)', type: 'json', default: [], colSpan: 2 },
            { name: 'is_enabled', label: 'Enabled', type: 'checkbox', default: true },
            { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
          ]}
        />
      )}
      {activeTab === 'deliveries' && (
        <Panel title="Webhook deliveries" description="Signed delivery attempts and their responses">
          <DataTable
            columns={[
              { key: 'endpoint_id', label: 'Endpoint', render: (row) => <span className="font-mono text-[11px]">{row.endpoint_id?.slice(0, 8)}</span> },
              { key: 'outbox_event_id', label: 'Event', render: (row) => <span className="font-mono text-[11px]">{row.outbox_event_id?.slice(0, 8)}</span> },
              { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
              { key: 'response_status', label: 'HTTP', align: 'right' },
              { key: 'attempts', label: 'Attempts', align: 'right' },
              { key: 'last_error', label: 'Last error' },
            ]}
            rows={deliveries.rows}
            loading={deliveries.loading}
            empty={<EmptyState icon={Webhook} title="No deliveries yet" compact />}
          />
        </Panel>
      )}
      <Modal open={Boolean(detail)} onClose={() => setDetail(null)} title={`Audit · ${detail?.action ?? ''}`} size="lg">
        {detail && (
          <div className="grid gap-4">
            <div className="grid gap-1 text-xs">
              <span className="font-semibold text-ink">{detail.actor_email}</span>
              <span className="text-muted">{dateTimeLabel(detail.created_at)} · {detail.entity_type} · {detail.entity_id}</span>
            </div>
            <div>
              <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-muted">Before</p>
              <JsonBlock value={detail.before_state} />
            </div>
            <div>
              <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-muted">After</p>
              <JsonBlock value={detail.after_state} />
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

const STATUTORY_TABS = [
  { key: 'returns', label: 'GST returns' },
  { key: 'itc', label: 'ITC reconciliation' },
  { key: 'einvoices', label: 'E-invoices' },
  { key: 'waybills', label: 'E-waybills' },
]

export function StatutoryPage() {
  const [tab, setTab] = useState('returns')
  const [registrationId, setRegistrationId] = useState('')
  const [invoiceId, setInvoiceId] = useState('')
  const [returnType, setReturnType] = useState('GSTR1')
  const [filingPeriod, setFilingPeriod] = useState(today().slice(0, 7))
  const [itcPeriod, setItcPeriod] = useState(today().slice(0, 7))
  const [transportMode, setTransportMode] = useState('road')
  const [validDays, setValidDays] = useState(10)
  const [acknowledgement, setAcknowledgement] = useState('')
  const [fileTarget, setFileTarget] = useState(null)
  const [cancelTarget, setCancelTarget] = useState(null)
  const [cancelReason, setCancelReason] = useState('')
  const [busy, setBusy] = useState(false)

  const returns = usePaged('/finance/gst/returns')
  const [itc, setItc] = useState({ rows: [], total: 0, loading: false })
  const einvoices = usePaged('/finance/e-invoices')
  const waybills = usePaged('/finance/e-waybills')

  const buildReturn = async () => {
    if (!registrationId || !filingPeriod) return
    setBusy(true)
    try {
      await api.post('/finance/gst/returns/build', {
        registration_id: registrationId,
        return_type: returnType,
        filing_period: filingPeriod,
      })
      toast.success('GST return built', `${returnType} · ${filingPeriod}`)
      returns.reload()
    } catch (error) {
      toast.error('Could not build GST return', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const fileReturn = async () => {
    if (!fileTarget || acknowledgement.length < 4) return
    setBusy(true)
    try {
      await api.post(`/finance/gst/returns/${fileTarget.id}/file`, { acknowledgement_number: acknowledgement })
      toast.success('Return filed', acknowledgement)
      setFileTarget(null)
      setAcknowledgement('')
      returns.reload()
    } catch (error) {
      toast.error('Could not file return', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const reconcileItc = async () => {
    if (!itcPeriod) return
    setBusy(true)
    try {
      const { data } = await api.post('/finance/gst/itc/reconcile', null, { params: { filing_period: itcPeriod } })
      setItc((current) => ({ ...current, rows: data.items ?? [], total: data.total ?? 0 }))
      toast.success('ITC reconciled', `${data.items?.length ?? 0} vendor lines checked`)
    } catch (error) {
      toast.error('Could not reconcile ITC', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const generateEinvoice = async () => {
    if (!invoiceId) return
    setBusy(true)
    try {
      const { data } = await api.post('/finance/e-invoices/generate', { invoice_id: invoiceId })
      toast.success('E-invoice generated', data.irn)
      einvoices.reload()
    } catch (error) {
      toast.error('Could not generate e-invoice', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const cancelEinvoice = async () => {
    if (!cancelTarget || cancelReason.length < 3) return
    setBusy(true)
    try {
      await api.post(`/finance/e-invoices/${cancelTarget.id}/cancel`, { reason: cancelReason })
      toast.success('E-invoice cancelled', cancelReason)
      setCancelTarget(null)
      setCancelReason('')
      einvoices.reload()
    } catch (error) {
      toast.error('Could not cancel e-invoice', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  const createWaybill = async () => {
    if (!invoiceId) return
    setBusy(true)
    try {
      const { data } = await api.post('/finance/e-waybills', {
        invoice_id: invoiceId,
        transport_mode: transportMode,
        valid_days: Number(validDays),
      })
      toast.success('E-waybill created', data.waybill_number)
      waybills.reload()
    } catch (error) {
      toast.error('Could not create e-waybill', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Finance · Statutory"
        title="GST and e-invoicing"
        description="Build returns from posted tax lines, reconcile credit, and generate IRN/e-waybill records."
      />
      <Tabs items={STATUTORY_TABS} value={tab} onChange={setTab} />
      {tab === 'returns' && (
        <div className="grid gap-4">
          <Panel title="Build a return" description="Returns are derived from posted sales and purchase tax lines.">
            <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-4">
              <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
                Registration
                <RemoteSelect lookup="taxRegistrations" value={registrationId} onChange={setRegistrationId} />
              </label>
              <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
                Return type
                <select className="input" value={returnType} onChange={(event) => setReturnType(event.target.value)}>
                  <option value="GSTR1">GSTR1</option>
                  <option value="GSTR3B">GSTR3B</option>
                </select>
              </label>
              <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
                Filing period
                <input className="input" placeholder="YYYY-MM" value={filingPeriod} onChange={(event) => setFilingPeriod(event.target.value)} />
              </label>
              <div className="flex items-end">
                <button type="button" className="btn-primary w-full" onClick={buildReturn} disabled={busy || !registrationId}>
                  <BadgeIndianRupee size={15} /> Build return
                </button>
              </div>
            </div>
          </Panel>
          <Panel title="Filed and draft returns" description={`${returns.total} returns on record`}>
            <DataTable
              columns={[
                { key: 'filing_period', label: 'Period' },
                { key: 'return_type', label: 'Type' },
                { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
                { key: 'gstin', label: 'GSTIN', render: (row) => row.summary?.gstin ?? '—' },
                { key: 'net_tax_liability', label: 'Net tax', align: 'right', render: (row) => money(row.summary?.net_tax_liability, { precise: true }) },
                { key: 'acknowledgement_number', label: 'Acknowledgement' },
              ]}
              rows={returns.rows}
              loading={returns.loading}
              empty={<EmptyState icon={FileText} title="No GST returns yet" compact />}
              rowActions={(row) =>
                row.status !== 'filed' ? (
                  <button
                    type="button"
                    className="btn-secondary py-1 text-xs"
                    onClick={() => {
                      setFileTarget(row)
                      setAcknowledgement('')
                    }}
                  >
                    File
                  </button>
                ) : null
              }
            />
          </Panel>
        </div>
      )}
      {tab === 'itc' && (
        <Panel
          title="Input tax credit reconciliation"
          description="Matches vendor tax lines to posted ITC entries."
          actions={
            <button type="button" className="btn-primary" onClick={reconcileItc} disabled={busy || !itcPeriod}>
              <RefreshCw size={15} /> Reconcile
            </button>
          }
        >
          <div className="px-5 py-4">
            <label className="grid max-w-xs gap-1.5 text-xs font-semibold text-ink-soft">
              Filing period
              <input className="input" placeholder="YYYY-MM" value={itcPeriod} onChange={(event) => setItcPeriod(event.target.value)} />
            </label>
          </div>
          <DataTable
            columns={[
              { key: 'filing_period', label: 'Period' },
              { key: 'source_document_id', label: 'Vendor invoice', render: (row) => <span className="font-mono text-[11px]">{row.source_document_id?.slice(0, 8)}</span> },
              { key: 'taxable_amount', label: 'Taxable', align: 'right', render: (row) => money(row.taxable_amount, { precise: true }) },
              { key: 'invoice_tax', label: 'Invoice tax', align: 'right', render: (row) => money(row.invoice_tax, { precise: true }) },
              { key: 'posted_itc', label: 'Posted ITC', align: 'right', render: (row) => money(row.posted_itc, { precise: true }) },
              { key: 'difference', label: 'Difference', align: 'right', render: (row) => money(row.difference, { precise: true }) },
              { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
            ]}
            rows={itc.rows}
            loading={itc.loading}
            empty={<EmptyState icon={BadgeIndianRupee} title="No ITC rows for this period" compact />}
          />
        </Panel>
      )}
      {tab === 'einvoices' && (
        <div className="grid gap-4">
          <Panel title="Generate e-invoice" description="Creates a signed IRN and QR payload for a posted invoice.">
            <div className="grid gap-4 p-5 sm:grid-cols-[1fr_auto]">
              <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
                Invoice
                <RemoteSelect lookup="invoices" value={invoiceId} onChange={setInvoiceId} />
              </label>
              <div className="flex items-end">
                <button type="button" className="btn-primary" onClick={generateEinvoice} disabled={busy || !invoiceId}>
                  <FileText size={15} /> Generate IRN
                </button>
              </div>
            </div>
          </Panel>
          <Panel title="Generated e-invoices" description={`${einvoices.total} records`}>
            <DataTable
              columns={[
                { key: 'irn', label: 'IRN', render: (row) => <span className="font-mono text-[11px]">{row.irn}</span> },
                { key: 'invoice_id', label: 'Invoice', render: (row) => <span className="font-mono text-[11px]">{row.invoice_id?.slice(0, 8)}</span> },
                { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
                { key: 'acknowledgement_number', label: 'Acknowledgement' },
              ]}
              rows={einvoices.rows}
              loading={einvoices.loading}
              empty={<EmptyState icon={FileText} title="No e-invoices yet" compact />}
              rowActions={(row) =>
                row.status !== 'cancelled' ? (
                  <button
                    type="button"
                    className="btn-secondary py-1 text-xs"
                    onClick={() => {
                      setCancelTarget(row)
                      setCancelReason('')
                    }}
                  >
                    Cancel
                  </button>
                ) : null
              }
            />
          </Panel>
        </div>
      )}
      {tab === 'waybills' && (
        <div className="grid gap-4">
          <Panel title="Create e-waybill" description="Generates a transport document for an invoice.">
            <div className="grid gap-4 p-5 sm:grid-cols-2 lg:grid-cols-4">
              <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
                Invoice
                <RemoteSelect lookup="invoices" value={invoiceId} onChange={setInvoiceId} />
              </label>
              <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
                Transport mode
                <select className="input" value={transportMode} onChange={(event) => setTransportMode(event.target.value)}>
                  <option value="road">Road</option>
                  <option value="air">Air</option>
                  <option value="rail">Rail</option>
                  <option value="ship">Ship</option>
                </select>
              </label>
              <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
                Valid days
                <input className="input" type="number" min="1" max="90" value={validDays} onChange={(event) => setValidDays(event.target.value)} />
              </label>
              <div className="flex items-end">
                <button type="button" className="btn-primary w-full" onClick={createWaybill} disabled={busy || !invoiceId}>
                  <Truck size={15} /> Create e-waybill
                </button>
              </div>
            </div>
          </Panel>
          <Panel title="E-waybills" description={`${waybills.total} transport documents`}>
            <DataTable
              columns={[
                { key: 'waybill_number', label: 'Waybill', render: (row) => <span className="font-mono text-[11px]">{row.waybill_number}</span> },
                { key: 'invoice_id', label: 'Invoice', render: (row) => <span className="font-mono text-[11px]">{row.invoice_id?.slice(0, 8)}</span> },
                { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
                { key: 'valid_until', label: 'Valid until', render: (row) => dateLabel(row.valid_until) },
              ]}
              rows={waybills.rows}
              loading={waybills.loading}
              empty={<EmptyState icon={Truck} title="No e-waybills yet" compact />}
            />
          </Panel>
        </div>
      )}
      <Modal
        open={Boolean(fileTarget)}
        onClose={() => !busy && setFileTarget(null)}
        title="File GST return"
        description={fileTarget ? `${fileTarget.return_type} · ${fileTarget.filing_period}` : ''}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setFileTarget(null)} disabled={busy}>Cancel</button>
            <button type="button" className="btn-primary" onClick={fileReturn} disabled={busy || acknowledgement.length < 4}>
              {busy ? 'Filing…' : 'Confirm filing'}
            </button>
          </>
        }
      >
        <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
          Portal acknowledgement number
          <input className="input" value={acknowledgement} onChange={(event) => setAcknowledgement(event.target.value)} placeholder="ACK-2026-0001" />
        </label>
      </Modal>
      <Modal
        open={Boolean(cancelTarget)}
        onClose={() => !busy && setCancelTarget(null)}
        title="Cancel e-invoice"
        description="Cancellation is recorded in the audit and outbox trail."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setCancelTarget(null)} disabled={busy}>Keep invoice</button>
            <button type="button" className="btn-primary" onClick={cancelEinvoice} disabled={busy || cancelReason.length < 3}>
              {busy ? 'Cancelling…' : 'Cancel IRN'}
            </button>
          </>
        }
      >
        <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
          Reason
          <textarea className="input min-h-24" value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} />
        </label>
      </Modal>
    </>
  )
}

export function BankFeedsPage() {
  const imports = usePaged('/finance/bank-feed-imports')
  const [importTarget, setImportTarget] = useState(null)
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)

  const upload = async () => {
    if (!importTarget || !file) return
    setBusy(true)
    try {
      const body = new FormData()
      body.append('file', file)
      const { data } = await api.post(`/finance/bank-feeds/${importTarget.id}/import`, body)
      toast.success('Bank feed imported', `${data.imported_count} imported · ${data.duplicate_count} duplicates skipped`)
      setImportTarget(null)
      setFile(null)
      imports.reload()
    } catch (error) {
      toast.error('Could not import bank feed', apiErrorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <ResourcePage
        eyebrow="Finance · Integrations"
        title="Bank feeds"
        description="Configure signed CSV, OFX, and webhook feeds, then import them idempotently."
        endpoint="/finance/bank-feeds"
        permission="finance.bankfeed"
        createLabel="Add feed"
        searchPlaceholder="Search feeds…"
        columns={[
          { key: 'name', label: 'Feed' },
          { key: 'provider', label: 'Provider', render: (row) => <Badge>{row.provider}</Badge> },
          { key: 'bank_account_id', label: 'Bank account', render: (row) => <span className="font-mono text-[11px]">{row.bank_account_id?.slice(0, 8)}</span> },
          { key: 'is_enabled', label: 'Status', render: (row) => <Badge>{row.is_enabled ? 'active' : 'disabled'}</Badge> },
          { key: 'last_imported_at', label: 'Last import', render: (row) => dateTimeLabel(row.last_imported_at) },
        ]}
        fields={[
          { name: 'name', label: 'Feed name', required: true },
          {
            name: 'provider',
            label: 'Provider',
            type: 'select',
            required: true,
            options: [
              { value: 'csv', label: 'CSV' },
              { value: 'ofx', label: 'OFX' },
              { value: 'webhook', label: 'Signed webhook' },
            ],
          },
          { name: 'bank_account_id', label: 'Bank account', type: 'reference', lookup: 'bankAccounts', required: true },
          { name: 'config', label: 'Provider config (JSON)', type: 'json', default: {}, colSpan: 2 },
          { name: 'webhook_secret', label: 'Webhook signing secret', help: 'Required for signed webhook feeds.' },
          { name: 'is_enabled', label: 'Enabled', type: 'checkbox', default: true },
        ]}
        rowActions={[
          {
            label: 'Import',
            icon: Upload,
            onClick: (row) => {
              setImportTarget(row)
              setFile(null)
            },
          },
        ]}
      />
      <section className="card mt-4 overflow-hidden">
        <div className="border-b border-line px-5 py-4">
          <h2 className="display text-lg font-semibold text-ink">Import history</h2>
          <p className="mt-1 text-xs text-muted">Repeated files are detected by content hash and idempotency key.</p>
        </div>
        <DataTable
          columns={[
            { key: 'file_name', label: 'File' },
            { key: 'status', label: 'Status', render: (row) => <Badge>{row.status}</Badge> },
            { key: 'row_count', label: 'Rows', align: 'right' },
            { key: 'imported_count', label: 'Imported', align: 'right' },
            { key: 'duplicate_count', label: 'Duplicates', align: 'right' },
          ]}
          rows={imports.rows}
          loading={imports.loading}
          empty={<EmptyState icon={Upload} title="No imports yet" compact />}
        />
      </section>
      <Modal
        open={Boolean(importTarget)}
        onClose={() => !busy && setImportTarget(null)}
        title="Import bank statement"
        description={importTarget ? `${importTarget.name} · ${importTarget.provider}` : ''}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setImportTarget(null)} disabled={busy}>Cancel</button>
            <button type="button" className="btn-primary" onClick={upload} disabled={busy || !file}>
              {busy ? 'Importing…' : 'Import statement'}
            </button>
          </>
        }
      >
        <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
          Statement file
          <input
            className="input"
            type="file"
            accept=".csv,.ofx,.qfx,.txt"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
        </label>
      </Modal>
    </>
  )
}
