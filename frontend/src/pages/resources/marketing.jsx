import { Megaphone, Send, Users } from 'lucide-react'
import ResourcePage from '../../components/ResourcePage'
import { Money, Primary, Ref, Status, TypeBadge } from '../../components/cells'
import { dateLabel, num } from '../../lib/format'

const CHANNELS = ['whatsapp', 'email', 'sms', 'social', 'push']
const CAMPAIGN_STATUSES = ['draft', 'scheduled', 'running', 'paused', 'completed']

export function CampaignsPage() {
  return (
    <ResourcePage
      eyebrow="Growth"
      title="Campaigns"
      description="Marketing pushes across channels, with budget and spend tracking."
      endpoint="/marketing/campaigns"
      permission="marketing.campaign"
      createLabel="New campaign"
      searchPlaceholder="Search campaigns…"
      filters={[{ name: 'status', label: 'All statuses', options: CAMPAIGN_STATUSES }]}
      emptyIcon={Megaphone}
      columns={[
        { key: 'name', label: 'Campaign', render: (row) => <Primary title={row.name} subtitle={row.goal || 'No goal set'} /> },
        { key: 'channel', label: 'Channel', render: (row) => <TypeBadge value={row.channel} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'start_date', label: 'Starts', render: (row) => dateLabel(row.start_date) },
        { key: 'budget', label: 'Budget', align: 'right', render: (row) => <Money value={row.budget} /> },
        {
          key: 'spend',
          label: 'Spend',
          render: (row) => {
            const budget = Number(row.budget ?? 0)
            const spend = Number(row.spend ?? 0)
            const pct = budget ? Math.min((spend / budget) * 100, 100) : 0
            return (
              <div className="min-w-[110px]">
                <div className="flex items-center justify-between text-[11px] font-semibold text-muted">
                  <span>{num(spend)}</span>
                  <span>{Math.round(pct)}%</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full rounded-full bg-gold" style={{ width: `${pct}%` }} />
                </div>
              </div>
            )
          },
        },
      ]}
      fields={[
        { name: 'name', label: 'Campaign name', required: true, colSpan: 2 },
        { name: 'channel', label: 'Channel', type: 'select', options: CHANNELS, default: 'whatsapp', required: true },
        { name: 'status', label: 'Status', type: 'select', options: CAMPAIGN_STATUSES, default: 'draft', required: true },
        { name: 'start_date', label: 'Start date', type: 'date' },
        { name: 'end_date', label: 'End date', type: 'date' },
        { name: 'budget', label: 'Budget', type: 'number', default: 0 },
        { name: 'spend', label: 'Spend', type: 'number', default: 0 },
        { name: 'goal', label: 'Goal', colSpan: 2 },
        { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
      ]}
    />
  )
}

export function SegmentsPage() {
  return (
    <ResourcePage
      eyebrow="Growth"
      title="Segments"
      description="Reusable audience definitions for targeted sends."
      endpoint="/marketing/segments"
      permission="marketing.segment"
      createLabel="New segment"
      searchPlaceholder="Search segments…"
      emptyIcon={Users}
      columns={[
        { key: 'name', label: 'Segment', render: (row) => <Primary title={row.name} subtitle={row.description || 'No description'} /> },
        {
          key: 'filters',
          label: 'Filters',
          render: (row) => (
            <code className="rounded bg-surface-2 px-2 py-1 text-[10px] text-ink-soft">
              {JSON.stringify(row.filters ?? {}).slice(0, 60)}
            </code>
          ),
        },
        { key: 'is_active', label: 'Status', render: (row) => <Status value={row.is_active ? 'active' : 'inactive'} /> },
        { key: 'created_at', label: 'Created', render: (row) => dateLabel(row.created_at) },
      ]}
      fields={[
        { name: 'name', label: 'Segment name', required: true, colSpan: 2 },
        { name: 'description', label: 'Description', type: 'textarea', colSpan: 2 },
        { name: 'filters', label: 'Filters (JSON)', type: 'json', default: '{}', colSpan: 2, help: 'Example: {"whatsapp_opt_in": true, "city": "Bengaluru"}' },
      ]}
    />
  )
}

export function CampaignSendsPage() {
  return (
    <ResourcePage
      eyebrow="Growth"
      title="Campaign sends"
      description="Execution records for each campaign and audience combination."
      endpoint="/marketing/sends"
      permission="marketing.campaignsend"
      createLabel="Schedule send"
      filters={[{ name: 'status', label: 'All statuses', options: ['scheduled', 'running', 'completed', 'failed'] }]}
      emptyIcon={Send}
      columns={[
        { key: 'campaign_id', label: 'Campaign', render: (row) => <Ref lookup="campaigns" id={row.campaign_id} /> },
        { key: 'segment_id', label: 'Segment', render: (row) => <Ref lookup="segments" id={row.segment_id} /> },
        { key: 'channel', label: 'Channel', render: (row) => <TypeBadge value={row.channel} /> },
        { key: 'status', label: 'Status', render: (row) => <Status value={row.status} /> },
        { key: 'scheduled_at', label: 'Scheduled', render: (row) => (row.scheduled_at ? new Date(row.scheduled_at).toLocaleString('en-IN') : '—') },
        { key: 'sent_count', label: 'Sent', align: 'right', render: (row) => num(row.sent_count) },
        { key: 'delivered_count', label: 'Delivered', align: 'right', render: (row) => num(row.delivered_count) },
      ]}
      fields={[
        { name: 'campaign_id', label: 'Campaign', type: 'reference', lookup: 'campaigns', required: true },
        { name: 'segment_id', label: 'Segment', type: 'reference', lookup: 'segments' },
        { name: 'channel', label: 'Channel', type: 'select', options: CHANNELS, default: 'whatsapp', required: true },
        { name: 'status', label: 'Status', type: 'select', options: ['scheduled', 'running', 'completed', 'failed'], default: 'scheduled' },
        { name: 'scheduled_at', label: 'Scheduled at', type: 'datetime' },
      ]}
    />
  )
}
