import { useEffect, useState } from 'react'
import {
  Activity,
  Award,
  BarChart3,
  Building2,
  CheckCircle2,
  Contact as ContactIcon,
  Handshake,
  Inbox,
  MessageSquare,
  RefreshCw,
  Send,
  Sparkles,
  Target,
} from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { Money, Primary, Ref, Status, TypeBadge } from '../../components/cells'
import { api, apiErrorMessage } from '../../lib/api'
import { dateLabel } from '../../lib/format'
import { useAuth } from '../../store/auth'
import { toast } from '../../store/toast'
import { KpiCard, LoadingBlock, PageHeader, SectionCard } from '../../components/ui'

async function postAction(path, successTitle, successMessage) {
  try {
    await api.post(path, {})
    toast.success(successTitle, successMessage)
    return true
  } catch (error) {
    toast.error('Could not complete action', apiErrorMessage(error))
    return false
  }
}

export function CompaniesPage() {
  return (
    <ResourcePage
      eyebrow="Relationships"
      title="Companies"
      description="Accounts, prospects and partners in your commercial universe."
      endpoint="/crm/companies"
      permission="crm.company"
      createLabel="New company"
      searchPlaceholder="Search companies, industries…"
      emptyIcon={Building2}
      emptyTitle="No companies yet"
      emptyDescription="Add your first account to start building a relationship map."
      columns={[
        { key: 'name', label: 'Company', render: (row) => <Primary title={row.name} subtitle={row.industry || 'No industry set'} /> },
        { key: 'city', label: 'Location', render: (row) => [row.city, row.state].filter(Boolean).join(', ') || '—' },
        { key: 'email', label: 'Email' },
        { key: 'phone', label: 'Phone' },
        { key: 'annual_revenue', label: 'Annual revenue', align: 'right', render: (row) => <Money value={row.annual_revenue} /> },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'name', label: 'Company name', required: true, colSpan: 2 },
        { name: 'industry', label: 'Industry' },
        { name: 'website', label: 'Website', placeholder: 'https://' },
        { name: 'gstin', label: 'GSTIN' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'annual_revenue', label: 'Annual revenue', type: 'number', default: 0 },
        { name: 'city', label: 'City' },
        { name: 'state', label: 'State' },
        { name: 'country', label: 'Country', default: 'India' },
        { name: 'address', label: 'Address', type: 'textarea', colSpan: 2 },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function ContactsPage() {
  return (
    <ResourcePage
      eyebrow="Relationships"
      title="Contacts"
      description="The people behind every account, with channel preferences and notes."
      endpoint="/crm/contacts"
      permission="crm.contact"
      createLabel="New contact"
      searchPlaceholder="Search contacts…"
      emptyIcon={ContactIcon}
      emptyTitle="No contacts yet"
      columns={[
        { key: 'first_name', label: 'Contact', render: (row) => <Primary title={`${row.first_name} ${row.last_name ?? ''}`.trim()} subtitle={row.title || '—'} /> },
        { key: 'company_id', label: 'Company', render: (row) => <Ref lookup="companies" id={row.company_id} /> },
        { key: 'email', label: 'Email' },
        { key: 'phone', label: 'Phone' },
        { key: 'whatsapp_opt_in', label: 'WhatsApp', render: (row) => <Status value={row.whatsapp_opt_in ? 'active' : 'inactive'} /> },
        { key: 'created_at', label: 'Added', render: (row) => dateLabel(row.created_at) },
      ]}
      fields={[
        { name: 'company_id', label: 'Company', type: 'reference', lookup: 'companies' },
        { name: 'first_name', label: 'First name', required: true },
        { name: 'last_name', label: 'Last name' },
        { name: 'title', label: 'Job title' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'whatsapp_opt_in', label: 'WhatsApp opt-in', type: 'checkbox', help: 'Contact has consented to WhatsApp messages.' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

const LEAD_SOURCES = ['manual', 'whatsapp', 'instagram', 'facebook', 'website', 'referral', 'event', 'meta_lead_ads']
const LEAD_STATUSES = ['new', 'contacted', 'qualified', 'proposal', 'negotiation', 'won', 'lost', 'converted']

export function LeadsPage() {
  const can = useAuth((state) => state.can)
  return (
    <ResourcePage
      eyebrow="Relationships"
      title="Leads"
      description="Capture intent early, score it, and keep the next follow-up visible."
      endpoint="/crm/leads"
      permission="crm.lead"
      createLabel="New lead"
      searchPlaceholder="Search leads, companies…"
      emptyIcon={Target}
      emptyTitle="No leads captured"
      filters={[
        { name: 'status', label: 'All statuses', options: LEAD_STATUSES },
        { name: 'source', label: 'All sources', options: LEAD_SOURCES },
      ]}
      columns={[
        { key: 'name', label: 'Lead', render: (row) => <Primary title={row.name} subtitle={row.company_name || row.email || '—'} /> },
        { key: 'source', label: 'Source', render: (row) => <TypeBadge value={row.source} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'score', label: 'Score', align: 'right', render: (row) => <span className="font-bold tabular-nums text-ink">{row.score ?? 0}<span className="ml-1 text-[10px] font-semibold text-muted">{row.score_grade || ''}</span></span> },
        { key: 'estimated_value', label: 'Est. value', align: 'right', render: (row) => <Money value={row.estimated_value} /> },
        { key: 'next_follow_up', label: 'Next follow-up', render: (row) => dateLabel(row.next_follow_up) },
        { key: 'whatsapp_opt_in', label: 'WhatsApp', render: (row) => <Status value={row.consent_source ? 'verified' : row.whatsapp_opt_in ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'name', label: 'Lead name', required: true, colSpan: 2 },
        { name: 'company_name', label: 'Company' },
        { name: 'owner_id', label: 'Owner', type: 'reference', lookup: 'users' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'source', label: 'Source', type: 'select', options: LEAD_SOURCES, default: 'manual', required: true },
        { name: 'status', label: 'Status', type: 'select', options: LEAD_STATUSES, default: 'new', required: true },
        { name: 'estimated_value', label: 'Estimated value', type: 'number', default: 0 },
        { name: 'next_follow_up', label: 'Next follow-up', type: 'date' },
        { name: 'whatsapp_opt_in', label: 'WhatsApp opt-in', type: 'checkbox' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
      rowActions={[
        {
          label: 'Rescore',
          icon: RefreshCw,
          show: () => can('crm.lead.rescore'),
          onClick: async (row, { reload }) => {
            if (await postAction(`/crm/leads/${row.id}/rescore`, 'Lead rescored', 'The score explanation has been refreshed.')) reload()
          },
        },
        {
          label: 'Convert',
          icon: Handshake,
          show: (row) => can('crm.lead.convert') && !row.converted_deal_id && !['won', 'lost', 'converted'].includes(row.status),
          onClick: async (row, { reload }) => {
            if (await postAction(`/crm/leads/${row.id}/convert`, 'Lead converted', 'A deal, company and contact were created.')) reload()
          },
        },
      ]}
    />
  )
}

const DEAL_STAGES = ['qualification', 'proposal', 'negotiation', 'won', 'lost']

export function DealsPage() {
  const can = useAuth((state) => state.can)
  return (
    <ResourcePage
      eyebrow="Relationships"
      title="Deals"
      description="Pipeline by stage, value and confidence — the commercial forecast in one place."
      endpoint="/crm/deals"
      permission="crm.deal"
      createLabel="New deal"
      searchPlaceholder="Search deals…"
      emptyIcon={Handshake}
      emptyTitle="No deals in the pipeline"
      filters={[{ name: 'stage', label: 'All stages', options: DEAL_STAGES }]}
      columns={[
        { key: 'name', label: 'Deal', render: (row) => <Primary title={row.name} subtitle={row.expected_close_date ? `Closes ${dateLabel(row.expected_close_date)}` : 'No close date'} /> },
        { key: 'company_id', label: 'Company', render: (row) => <Ref lookup="companies" id={row.company_id} /> },
        { key: 'stage', label: 'Stage', render: (row) => <Status value={row.stage} /> },
        { key: 'amount', label: 'Amount', align: 'right', render: (row) => <Money value={row.amount} /> },
        { key: 'weighted_amount', label: 'Weighted', align: 'right', render: (row) => <Money value={row.weighted_amount} /> },
        { key: 'owner_id', label: 'Owner', render: (row) => <Ref lookup="users" id={row.owner_id} /> },
      ]}
      fields={[
        { name: 'name', label: 'Deal name', required: true, colSpan: 2 },
        { name: 'company_id', label: 'Company', type: 'reference', lookup: 'companies' },
        { name: 'contact_id', label: 'Primary contact', type: 'reference', lookup: 'contacts' },
        { name: 'lead_id', label: 'Source lead', type: 'reference', lookup: 'leads' },
        { name: 'owner_id', label: 'Owner', type: 'reference', lookup: 'users' },
        { name: 'stage', label: 'Stage', type: 'select', options: DEAL_STAGES, default: 'qualification', required: true },
        { name: 'amount', label: 'Amount', type: 'number', default: 0 },
        { name: 'probability', label: 'Probability %', type: 'number', default: 20, min: 0 },
        { name: 'expected_close_date', label: 'Expected close', type: 'date' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
      rowActions={[
        {
          label: 'Mark won',
          icon: Award,
          show: (row) => can('crm.deal.win') && !row.won_at && !row.lost_at,
          onClick: async (row, { reload }) => {
            if (await postAction(`/crm/deals/${row.id}/win`, 'Deal won', 'The pipeline and lead status were updated.')) reload()
          },
        },
      ]}
    />
  )
}

const ACTIVITY_TYPES = ['task', 'call', 'meeting', 'email', 'note']
const RELATED_ENTITIES = ['company', 'contact', 'lead', 'deal', 'ticket', 'order']

export function ActivitiesPage() {
  return (
    <ResourcePage
      eyebrow="Relationships"
      title="Activities"
      description="Calls, meetings and follow-ups linked to the records that matter."
      endpoint="/crm/activities"
      permission="crm.activity"
      createLabel="New activity"
      searchPlaceholder="Search activities…"
      columns={[
        { key: 'subject', label: 'Activity', render: (row) => <Primary title={row.subject} subtitle={row.related_entity ? `${row.related_entity} · ${String(row.related_id ?? '').slice(0, 8)}` : 'General'} /> },
        { key: 'activity_type', label: 'Type', render: (row) => <TypeBadge value={row.activity_type} /> },
        { key: 'due_at', label: 'Due', render: (row) => (row.due_at ? new Date(row.due_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—') },
        { key: 'completed', label: 'Status', render: (row) => <Status value={row.completed ? 'done' : 'pending'} /> },
        { key: 'owner_id', label: 'Owner', render: (row) => <Ref lookup="users" id={row.owner_id} /> },
      ]}
      fields={[
        { name: 'subject', label: 'Subject', required: true, colSpan: 2 },
        { name: 'activity_type', label: 'Type', type: 'select', options: ACTIVITY_TYPES, default: 'task' },
        { name: 'owner_id', label: 'Owner', type: 'reference', lookup: 'users' },
        { name: 'related_entity', label: 'Related to', type: 'select', options: RELATED_ENTITIES },
        { name: 'related_id', label: 'Related record ID', help: 'Paste the record UUID if linking to a specific entity.' },
        { name: 'due_at', label: 'Due at', type: 'datetime' },
        { name: 'completed', label: 'Completed', type: 'checkbox' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function InboxPage() {
  return (
    <ResourcePage
      eyebrow="Relationships"
      title="Unified inbox"
      description="WhatsApp and social conversations routed to one ownership queue with SLA timers."
      endpoint="/crm/inbox/conversations"
      permission="crm.inbox"
      searchPlaceholder="Search conversations…"
      emptyIcon={Inbox}
      emptyTitle="No conversations assigned"
      canCreate={false}
      canEdit={false}
      canDelete={false}
      fields={[]}
      filters={[{ name: 'status', label: 'All statuses', options: ['open', 'pending', 'closed'] }]}
      columns={[
        { key: 'conversation_key', label: 'Conversation', render: (row) => <Primary title={row.conversation_key} subtitle={row.external_ref || 'No external reference'} /> },
        { key: 'channel', label: 'Channel', render: (row) => <TypeBadge value={row.channel} /> },
        { key: 'lead_id', label: 'Lead', render: (row) => <Ref lookup="leads" id={row.lead_id} /> },
        { key: 'assignee_id', label: 'Owner', render: (row) => <Ref lookup="users" id={row.assignee_id} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'sla_due_at', label: 'SLA due', render: (row) => (row.sla_due_at ? dateLabel(row.sla_due_at) : '—') },
      ]}
    />
  )
}

const CALL_STATUSES = ['scheduled', 'completed', 'missed', 'cancelled']

export function CallsPage() {
  const can = useAuth((state) => state.can)
  return (
    <ResourcePage
      eyebrow="Relationships"
      title="Calls"
      description="Record calls, attach transcripts and generate coachable assessments."
      endpoint="/crm/calls"
      permission="crm.call"
      createLabel="New call"
      searchPlaceholder="Search calls…"
      emptyIcon={MessageSquare}
      emptyTitle="No calls recorded"
      canDelete={false}
      filters={[{ name: 'status', label: 'All statuses', options: CALL_STATUSES }]}
      columns={[
        { key: 'external_call_id', label: 'Call', render: (row) => <Primary title={row.external_call_id || `${row.direction} call`} subtitle={row.provider} /> },
        { key: 'lead_id', label: 'Lead', render: (row) => <Ref lookup="leads" id={row.lead_id} /> },
        { key: 'contact_id', label: 'Contact', render: (row) => <Ref lookup="contacts" id={row.contact_id} /> },
        { key: 'direction', label: 'Direction', render: (row) => <TypeBadge value={row.direction} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'duration_seconds', label: 'Duration', render: (row) => (row.duration_seconds ? `${Math.round(row.duration_seconds / 60)}m` : '—') },
      ]}
      fields={[
        { name: 'lead_id', label: 'Lead', type: 'reference', lookup: 'leads' },
        { name: 'contact_id', label: 'Contact', type: 'reference', lookup: 'contacts' },
        { name: 'deal_id', label: 'Deal', type: 'reference', lookup: 'deals' },
        { name: 'provider', label: 'Provider', default: 'manual', required: true },
        { name: 'external_call_id', label: 'External call ID' },
        { name: 'direction', label: 'Direction', type: 'select', options: ['inbound', 'outbound'], default: 'outbound' },
        { name: 'status', label: 'Status', type: 'select', options: CALL_STATUSES, default: 'completed' },
        { name: 'duration_seconds', label: 'Duration (seconds)', type: 'number', default: 0 },
        { name: 'recording_ref', label: 'Recording reference' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
      rowActions={[
        {
          label: 'Assess',
          icon: Sparkles,
          show: () => can('crm.call.assess'),
          onClick: async (row, { reload }) => {
            if (await postAction(`/crm/calls/${row.id}/assess`, 'Assessment generated', 'The coaching draft is ready for review.')) reload()
          },
        },
      ]}
    />
  )
}

export function CallAssessmentsPage() {
  return (
    <ResourcePage
      eyebrow="Relationships"
      title="Call assessments"
      description="Explainable coaching signals with human approval before they influence the CRM."
      endpoint="/crm/call-assessments"
      permission="crm.call"
      searchPlaceholder="Search assessments…"
      emptyIcon={Sparkles}
      emptyTitle="No assessments yet"
      canCreate={false}
      canEdit={false}
      canDelete={false}
      fields={[]}
      filters={[{ name: 'status', label: 'All statuses', options: ['draft', 'approved', 'rejected'] }]}
      columns={[
        { key: 'call_id', label: 'Call ID', render: (row) => <span className="font-mono text-xs">{String(row.call_id).slice(0, 8)}</span> },
        { key: 'score', label: 'Score', align: 'right', render: (row) => <span className="font-bold tabular-nums text-ink">{row.score}</span> },
        { key: 'summary', label: 'Summary', render: (row) => <span className="line-clamp-2">{row.summary}</span> },
        { key: 'next_best_action', label: 'Next action', render: (row) => <span className="line-clamp-2">{row.next_best_action}</span> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'reviewed_at', label: 'Reviewed', render: (row) => (row.reviewed_at ? dateLabel(row.reviewed_at) : '—') },
      ]}
    />
  )
}

export function SocialAccountsPage() {
  return (
    <ResourcePage
      eyebrow="Relationships"
      title="Social accounts"
      description="Connected social channels used for publishing and conversation sync."
      endpoint="/crm/social/accounts"
      permission="crm.socialaccount"
      createLabel="Connect account"
      searchPlaceholder="Search social accounts…"
      emptyIcon={Send}
      emptyTitle="No social accounts connected"
      columns={[
        { key: 'display_name', label: 'Account', render: (row) => <Primary title={row.display_name || row.external_account_id} subtitle={row.channel} /> },
        { key: 'channel', label: 'Channel', render: (row) => <TypeBadge value={row.channel} /> },
        { key: 'external_account_id', label: 'External ID' },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'channel', label: 'Channel', required: true, default: 'instagram' },
        { name: 'external_account_id', label: 'External account ID', required: true },
        { name: 'display_name', label: 'Display name' },
        { name: 'token_ref', label: 'Token reference' },
      ]}
    />
  )
}

export function SocialPostsPage() {
  const can = useAuth((state) => state.can)
  return (
    <ResourcePage
      eyebrow="Relationships"
      title="Social publishing"
      description="Draft, approve and publish social posts without bypassing human review."
      endpoint="/crm/social/posts"
      permission="crm.socialpost"
      searchPlaceholder="Search social posts…"
      emptyIcon={Send}
      emptyTitle="No social posts yet"
      canCreate={false}
      canEdit={false}
      canDelete={false}
      fields={[]}
      filters={[{ name: 'status', label: 'All statuses', options: ['draft', 'pending_approval', 'approved', 'published', 'failed'] }]}
      columns={[
        { key: 'body', label: 'Post', render: (row) => <Primary title={row.body} subtitle={row.scheduled_at ? `Scheduled ${dateLabel(row.scheduled_at)}` : 'No schedule'} /> },
        { key: 'account_id', label: 'Account', render: (row) => <span className="font-mono text-xs">{String(row.account_id).slice(0, 8)}</span> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'external_post_id', label: 'External post' },
        { key: 'published_at', label: 'Published', render: (row) => (row.published_at ? dateLabel(row.published_at) : '—') },
      ]}
      rowActions={[
        {
          label: 'Approve',
          icon: CheckCircle2,
          show: (row) => can('crm.socialpost.approve') && ['draft', 'pending_approval'].includes(row.status),
          onClick: async (row, { reload }) => {
            if (await postAction(`/crm/social/posts/${row.id}/approve`, 'Post approved', 'The post is ready to publish.')) reload()
          },
        },
        {
          label: 'Publish',
          icon: Send,
          show: (row) => can('crm.socialpost.publish') && ['approved', 'scheduled'].includes(row.status),
          onClick: async (row, { reload }) => {
            if (await postAction(`/crm/social/posts/${row.id}/publish`, 'Post published', 'The publish outcome was recorded.')) reload()
          },
        },
      ]}
    />
  )
}

export function PipelineReportPage() {
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    api
      .get('/crm/reports/pipeline')
      .then(({ data }) => {
        if (active) setReport(data)
      })
      .catch((requestError) => {
        if (active) setError(apiErrorMessage(requestError, 'Unable to load the pipeline report.'))
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <>
      <PageHeader
        eyebrow="Relationships"
        title="Pipeline report"
        description="Stage coverage and weighted forecast, derived from the live CRM pipeline."
      />
      {error ? (
        <div className="card p-6 text-sm font-semibold text-rose-600">{error}</div>
      ) : !report ? (
        <LoadingBlock label="Loading pipeline report…" />
      ) : (
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <KpiCard label="Open deals" value={report.total} icon={Handshake} />
            <KpiCard label="Weighted value" value={<Money value={report.weighted_amount} />} icon={BarChart3} tone="gold" />
            <KpiCard label="Tracked stages" value={report.stages?.length ?? 0} icon={Target} tone="sky" />
          </div>
          <SectionCard title="Stage breakdown" description="Pipeline concentration by stage.">
            <div className="divide-y divide-line">
              {(report.stages ?? []).map((stage) => (
                <div key={stage.code ?? stage.stage ?? stage.name} className="flex items-center justify-between gap-4 py-3">
                  <div>
                    <p className="text-sm font-bold text-ink">{stage.name ?? stage.code ?? stage.stage}</p>
                    <p className="text-xs text-muted">{stage.count ?? 0} deals</p>
                  </div>
                  <Money value={stage.amount ?? stage.weighted_amount ?? 0} />
                </div>
              ))}
            </div>
          </SectionCard>
        </div>
      )}
    </>
  )
}
