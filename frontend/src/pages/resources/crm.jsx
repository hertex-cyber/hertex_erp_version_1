import { Building2, Contact as ContactIcon, Handshake, Target } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { Money, Primary, Ref, Status, TypeBadge } from '../../components/cells'
import { dateLabel } from '../../lib/format'

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

const LEAD_SOURCES = ['manual', 'whatsapp', 'instagram', 'facebook', 'website', 'referral', 'event']
const LEAD_STATUSES = ['new', 'contacted', 'qualified', 'proposal', 'negotiation', 'won', 'lost']

export function LeadsPage() {
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
        { key: 'score', label: 'Score', align: 'right', render: (row) => <span className="font-bold tabular-nums text-ink">{row.score ?? 0}</span> },
        { key: 'estimated_value', label: 'Est. value', align: 'right', render: (row) => <Money value={row.estimated_value} /> },
        { key: 'next_follow_up', label: 'Next follow-up', render: (row) => dateLabel(row.next_follow_up) },
        { key: 'whatsapp_opt_in', label: 'WhatsApp', render: (row) => <Status value={row.whatsapp_opt_in ? 'active' : 'inactive'} /> },
      ]}
      fields={[
        { name: 'name', label: 'Lead name', required: true, colSpan: 2 },
        { name: 'company_name', label: 'Company' },
        { name: 'owner_id', label: 'Owner', type: 'reference', lookup: 'users' },
        { name: 'email', label: 'Email', type: 'email' },
        { name: 'phone', label: 'Phone' },
        { name: 'source', label: 'Source', type: 'select', options: LEAD_SOURCES, default: 'manual', required: true },
        { name: 'status', label: 'Status', type: 'select', options: LEAD_STATUSES, default: 'new', required: true },
        { name: 'score', label: 'Score', type: 'number', default: 0, min: 0 },
        { name: 'estimated_value', label: 'Estimated value', type: 'number', default: 0 },
        { name: 'next_follow_up', label: 'Next follow-up', type: 'date' },
        { name: 'whatsapp_opt_in', label: 'WhatsApp opt-in', type: 'checkbox' },
        { name: 'notes', label: 'Notes', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

const DEAL_STAGES = ['qualification', 'proposal', 'negotiation', 'won', 'lost']

export function DealsPage() {
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
        {
          key: 'probability',
          label: 'Confidence',
          render: (row) => (
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
                <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(Number(row.probability ?? 0), 100)}%` }} />
              </div>
              <span className="text-[11px] font-semibold text-muted">{row.probability ?? 0}%</span>
            </div>
          ),
        },
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
