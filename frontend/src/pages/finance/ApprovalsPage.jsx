import { useCallback, useEffect, useState } from 'react'
import { Check, CircleAlert, ClipboardCheck, RefreshCw, X } from 'lucide-react'
import { EmptyState, Modal, PageHeader, SectionCard, Spinner } from '../../components/ui'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel, money } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'

export default function ApprovalsPage() {
  const can = useAuth((state) => state.can)
  const user = useAuth((state) => state.user)
  const canRead = can('finance.approval.read')
  const canApprove = can('finance.approval.approve')
  const canReject = can('finance.approval.reject')
  const [approvals, setApprovals] = useState([])
  const [loading, setLoading] = useState(true)
  const [pageError, setPageError] = useState('')
  const [selected, setSelected] = useState(null)
  const [decision, setDecision] = useState('approve')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    if (!canRead) {
      setLoading(false)
      return
    }
    setLoading(true)
    setPageError('')
    try {
      const { data } = await api.get('/finance/approvals', { params: { status: 'pending', size: 200 } })
      setApprovals(data.items ?? [])
    } catch (error) {
      setPageError(apiErrorMessage(error, 'Could not load accounting approvals.'))
    } finally {
      setLoading(false)
    }
  }, [canRead])

  useEffect(() => { load() }, [load])

  const openDecision = (approval, nextDecision) => {
    setSelected(approval)
    setDecision(nextDecision)
    setReason('')
  }

  const submitDecision = async (event) => {
    event.preventDefault()
    if (!selected || reason.trim().length < 3) return
    setSaving(true)
    try {
      await api.post(`/finance/approvals/${selected.id}/${decision}`, { reason: reason.trim() })
      toast.success(
        decision === 'approve' ? 'Approval completed' : 'Request rejected',
        `${selected.summary} was ${decision === 'approve' ? 'approved' : 'rejected'}.`,
      )
      setSelected(null)
      await load()
    } catch (error) {
      toast.error('Could not decide approval', apiErrorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Finance controls"
        title="Approval queue"
        description="Review manual journals, vendor disbursements, and inventory adjustments submitted by another user."
        actions={<button type="button" className="btn-secondary" onClick={load} disabled={loading}><RefreshCw size={15} /> Refresh</button>}
      />
      {pageError ? (
        <EmptyState icon={CircleAlert} title="Could not load approvals" description={pageError} action={<button className="btn-primary" onClick={load} type="button">Try again</button>} />
      ) : (
        <SectionCard title="Pending requests" description={`${approvals.length} request${approvals.length === 1 ? '' : 's'} awaiting a decision.`}>
          {loading ? (
            <div className="flex min-h-48 items-center justify-center gap-3 text-sm text-muted"><Spinner /> Loading approvals…</div>
          ) : approvals.length ? (
            <div className="divide-y divide-line">
              {approvals.map((approval) => {
                const isRequester = approval.requested_by_id === user?.id
                const canDecide = !isRequester && (canApprove || canReject)
                return (
                  <article key={approval.id} className="flex flex-col gap-4 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <p className="font-semibold text-ink">{approval.summary}</p>
                      <p className="mt-1 text-xs capitalize text-muted">
                        {approval.entity_type.replaceAll('_', ' ')} · Requested {dateLabel(approval.created_at)}
                      </p>
                      <p className="mt-1 font-mono text-[11px] text-muted">{approval.entity_id}</p>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className="font-bold tabular-nums text-ink">{money(approval.amount)}</span>
                      {isRequester ? (
                        <span className="text-xs text-muted">You requested this</span>
                      ) : (
                        <>
                          {canApprove && <button type="button" className="btn-primary !px-3 !py-2" onClick={() => openDecision(approval, 'approve')}><Check size={14} /> Approve</button>}
                          {canReject && <button type="button" className="btn-secondary !px-3 !py-2" onClick={() => openDecision(approval, 'reject')}><X size={14} /> Reject</button>}
                          {!canDecide && <span className="text-xs text-muted">Decision access restricted</span>}
                        </>
                      )}
                    </div>
                  </article>
                )
              })}
            </div>
          ) : (
            <EmptyState compact icon={ClipboardCheck} title="No pending approvals" description="New requests will appear here when submitted." />
          )}
        </SectionCard>
      )}
      <Modal
        open={Boolean(selected)}
        onClose={() => !saving && setSelected(null)}
        title={decision === 'approve' ? 'Approve request' : 'Reject request'}
        description={selected?.summary ?? ''}
        size="md"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setSelected(null)} disabled={saving}>Cancel</button>
            <button type="submit" form="finance-approval-decision" className={decision === 'approve' ? 'btn-primary' : 'btn-danger'} disabled={saving || reason.trim().length < 3}>
              {saving ? 'Saving…' : decision === 'approve' ? 'Confirm approval' : 'Confirm rejection'}
            </button>
          </>
        }
      >
        <form id="finance-approval-decision" onSubmit={submitDecision} className="grid gap-3">
          <label className="grid gap-1.5 text-xs font-semibold text-ink-soft">
            Decision reason
            <textarea className="input min-h-24" value={reason} onChange={(event) => setReason(event.target.value)} minLength={3} maxLength={500} required />
          </label>
        </form>
      </Modal>
    </>
  )
}
