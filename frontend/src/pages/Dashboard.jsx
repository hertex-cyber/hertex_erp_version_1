import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Banknote,
  Boxes,
  CircleDollarSign,
  Clock,
  FileText,
  FolderKanban,
  Handshake,
  LifeBuoy,
  Package,
  Receipt,
  ShoppingBag,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  Wallet,
} from 'lucide-react'
import { api, apiErrorMessage } from '../lib/api'
import { compactMoney, dateTimeLabel, money, num, titleCase } from '../lib/format'
import { useAuth } from '../store/auth'
import { EmptyState, KpiCard, PageHeader, SectionCard, Spinner } from '../components/ui'

const CHART_COLORS = ['#174f3f', '#c25c39', '#c2953f', '#4f7f6c', '#8f5d4b', '#7a877f']

function ChartTooltip({ active, payload, label, valueFormatter = money }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-line bg-surface px-3.5 py-2.5 shadow-[var(--shadow-card)]">
      <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.12em] text-muted">{label}</p>
      {payload.map((item) => (
        <p key={item.dataKey} className="flex items-center gap-2 text-xs font-semibold text-ink">
          <span className="h-2 w-2 rounded-full" style={{ background: item.color ?? item.fill }} />
          {titleCase(item.name)}: {valueFormatter(item.value)}
        </p>
      ))}
    </div>
  )
}

function Hero({ kpis, user }) {
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const firstName = user?.full_name?.split(' ')[0] ?? 'there'

  return (
    <div className="forest-grid relative overflow-hidden rounded-3xl p-6 text-white shadow-[var(--shadow-float)] sm:p-8">
      <div className="absolute -right-20 -top-24 h-72 w-72 rounded-full border border-white/10" />
      <div className="absolute right-16 top-10 h-40 w-40 rounded-full border border-gold/20" />
      <div className="absolute bottom-[-120px] right-[-40px] h-72 w-72 rounded-full bg-gold/10 blur-2xl" />
      <div className="relative flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-gold">
            {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
          <h1 className="display mt-3 text-3xl font-medium leading-tight text-white sm:text-4xl">
            {greeting}, {firstName}.
          </h1>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-white/50">
            Here’s the pulse of the business — revenue, cash, stock and the work that needs attention today.
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            <Link to="/sales/orders" className="inline-flex items-center gap-2 rounded-xl bg-gold px-4 py-2.5 text-xs font-bold text-forest transition hover:bg-[#d3a64f]">
              <ShoppingBag size={15} /> New sales order
            </Link>
            <Link to="/assistant" className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/[0.06] px-4 py-2.5 text-xs font-bold text-white/80 transition hover:bg-white/[0.12] hover:text-white">
              <Sparkles size={15} className="text-gold" /> Ask the assistant
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:min-w-[440px]">
          {[
            ['Revenue', compactMoney(kpis.revenue), 'this period'],
            ['Receivables', compactMoney(kpis.receivables), 'outstanding'],
            ['Collected', compactMoney(kpis.cash_collected), 'cash in'],
            ['Pipeline', compactMoney(kpis.pipeline_value), 'open deals'],
            ['Stock value', compactMoney(kpis.stock_value), 'on hand'],
            ['Payables', compactMoney(kpis.payables), 'to suppliers'],
          ].map(([label, value, hint]) => (
            <div key={label} className="rounded-2xl border border-white/10 bg-white/[0.055] p-3.5 backdrop-blur">
              <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-white/35">{label}</p>
              <p className="display mt-1.5 text-lg font-semibold text-white">{value}</p>
              <p className="mt-0.5 text-[9px] font-medium text-white/30">{hint}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function ActivityList({ items }) {
  if (!items?.length) return <EmptyState compact title="No activity yet" description="Audit events will appear here as the team works." />
  const iconFor = (module) => {
    const map = { sales: ShoppingBag, finance: CircleDollarSign, crm: Handshake, inventory: Package, support: LifeBuoy, hr: Users, procurement: Receipt, projects: FolderKanban }
    return map[module] ?? FileText
  }
  return (
    <div className="divide-y divide-line">
      {items.slice(0, 7).map((item) => {
        const Icon = iconFor(item.module)
        return (
          <div key={item.id} className="flex items-start gap-3 px-5 py-3.5">
            <span className="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-surface-2 text-muted ring-1 ring-line">
              <Icon size={14} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs text-ink-soft">
                <span className="font-bold text-ink">{item.actor_email?.split('@')[0] ?? 'Someone'}</span>{' '}
                {titleCase(item.action)} {titleCase(item.entity).toLowerCase()}
              </p>
              <p className="mt-0.5 text-[10px] text-muted">{titleCase(item.module)} · {dateTimeLabel(item.created_at)}</p>
            </div>
            <span className="badge bg-surface-2 text-muted ring-line">{item.module}</span>
          </div>
        )
      })}
    </div>
  )
}

function InsightsPanel({ insights }) {
  if (!insights?.length) return null
  const tones = {
    critical: 'border-rose-200 bg-rose-50 text-rose-700',
    warning: 'border-amber-200 bg-amber-50 text-amber-700',
    info: 'border-sky-200 bg-sky-50 text-sky-700',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  }
  return (
    <SectionCard
      title="Assistant insights"
      description="Signals worth looking at right now."
      action={<Link to="/assistant" className="text-[11px] font-bold text-primary hover:underline">Open assistant</Link>}
    >
      <div className="divide-y divide-line">
        {insights.slice(0, 4).map((insight) => (
          <div key={insight.title} className="flex items-start gap-3 px-5 py-4">
            <span className={`mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border ${tones[insight.severity] ?? tones.info}`}>
              <AlertTriangle size={14} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-bold text-ink">{insight.title}</p>
              <p className="mt-0.5 text-[11px] leading-relaxed text-muted">{insight.detail}</p>
              <p className="mt-1.5 text-[10px] font-semibold text-primary">{insight.action}</p>
            </div>
            {insight.metric && <span className="badge bg-surface-2 text-muted ring-line">{insight.metric}</span>}
          </div>
        ))}
      </div>
    </SectionCard>
  )
}

export default function Dashboard() {
  const user = useAuth((state) => state.user)
  const [data, setData] = useState(null)
  const [insights, setInsights] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const load = () => {
    setLoading(true)
    setError(null)
    Promise.all([
      api.get('/analytics/dashboard'),
      api.get('/ai/insights').catch(() => ({ data: { insights: [] } })),
    ])
      .then(([dashboard, insightResponse]) => {
        setData(dashboard.data)
        setInsights(insightResponse.data?.insights ?? [])
      })
      .catch((requestError) => setError(apiErrorMessage(requestError, 'Could not load the command centre.')))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="shimmer h-64 rounded-3xl" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => <div key={index} className="shimmer h-32 rounded-2xl" />)}
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="shimmer h-80 rounded-2xl" />
          <div className="shimmer h-80 rounded-2xl" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <EmptyState
        title="Command centre unavailable"
        description={error}
        action={<button type="button" className="btn-primary" onClick={load}>Try again</button>}
      />
    )
  }

  const { kpis, revenue_trend: trend = [], pipeline = [], channels = [], recent_activity: activity = [] } = data
  const totalChannelOrders = channels.reduce((sum, channel) => sum + Number(channel.orders ?? 0), 0)
  const leadToDeal = kpis.lead_count ? Math.round((kpis.open_deals / Math.max(kpis.lead_count, 1)) * 100) : 0

  return (
    <div className="space-y-6">
      <Hero kpis={kpis} user={user} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 stagger">
        <KpiCard label="Revenue" value={money(kpis.revenue)} hint="posted invoices" icon={CircleDollarSign} tone="primary" delta={12.4} spark={trend.map((point) => Number(point.revenue))} />
        <KpiCard label="Receivables" value={money(kpis.receivables)} hint="awaiting collection" icon={Wallet} tone="accent" delta={-3.1} />
        <KpiCard label="Cash collected" value={money(kpis.cash_collected)} hint="payments received" icon={Banknote} tone="gold" delta={8.7} spark={[4, 6, 5, 8, 7, 9, 11]} />
        <KpiCard label="Pipeline" value={money(kpis.pipeline_value)} hint={`${kpis.open_deals} open deals`} icon={Handshake} tone="sky" delta={5.2} spark={pipeline.map((stage) => Number(stage.amount))} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <SectionCard
          className="lg:col-span-2"
          title="Revenue rhythm"
          description="Invoiced revenue and order volume over recent months."
          action={<span className="badge bg-primary-soft text-primary ring-primary/10"><TrendingUp size={11} /> Trend</span>}
        >
          <div className="h-[300px] px-2 pb-4 pt-5">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trend} margin={{ top: 8, right: 18, left: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#174f3f" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="#174f3f" stopOpacity={0.01} />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} stroke="#ece6db" strokeDasharray="3 5" />
                <XAxis dataKey="month" tickLine={false} axisLine={false} dy={8} />
                <YAxis tickLine={false} axisLine={false} tickFormatter={compactMoney} width={62} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="revenue" name="Revenue" stroke="#174f3f" strokeWidth={2.4} fill="url(#revenueFill)" dot={false} activeDot={{ r: 4, strokeWidth: 2, fill: '#fffdfa' }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Channel mix" description={`${num(totalChannelOrders)} orders across channels.`}>
          <div className="h-[210px] px-2 pt-4">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={channels} dataKey="orders" nameKey="channel" innerRadius={52} outerRadius={78} paddingAngle={3} stroke="none">
                  {channels.map((entry, index) => (
                    <Cell key={entry.channel} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip content={<ChartTooltip valueFormatter={(value) => `${num(value)} orders`} />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="space-y-2 px-5 pb-5">
            {channels.slice(0, 4).map((channel, index) => (
              <div key={channel.channel} className="flex items-center gap-2 text-[11px]">
                <span className="h-2 w-2 rounded-full" style={{ background: CHART_COLORS[index % CHART_COLORS.length] }} />
                <span className="flex-1 capitalize text-ink-soft">{channel.channel}</span>
                <span className="font-bold tabular-nums text-ink">{money(channel.revenue)}</span>
              </div>
            ))}
            {!channels.length && <p className="text-xs text-muted">No channel data yet.</p>}
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <SectionCard
          className="lg:col-span-2"
          title="Pipeline by stage"
          description="Where value is sitting in the commercial funnel."
          action={<Link to="/crm/deals" className="text-[11px] font-bold text-primary hover:underline">Open deals</Link>}
        >
          <div className="h-[260px] px-2 pb-4 pt-5">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={pipeline} layout="vertical" margin={{ top: 0, right: 24, left: 10, bottom: 0 }}>
                <CartesianGrid horizontal={false} stroke="#ece6db" strokeDasharray="3 5" />
                <XAxis type="number" tickLine={false} axisLine={false} tickFormatter={compactMoney} />
                <YAxis type="category" dataKey="stage" tickLine={false} axisLine={false} width={92} tickFormatter={titleCase} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="amount" name="Amount" fill="#c25c39" radius={[0, 8, 8, 0]} barSize={18}>
                  {pipeline.map((entry, index) => (
                    <Cell key={entry.stage} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        <SectionCard title="Signals" description="Small numbers that need a look.">
          <div className="grid grid-cols-2 gap-3 p-4">
            {[
              { label: 'Low stock', value: kpis.low_stock_count, icon: Boxes, to: '/inventory/stock', tone: 'text-accent bg-accent-soft' },
              { label: 'Open tickets', value: kpis.open_tickets, icon: LifeBuoy, to: '/support', tone: 'text-sky-700 bg-sky-50' },
              { label: 'Active projects', value: kpis.active_projects, icon: FolderKanban, to: '/projects/projects', tone: 'text-primary bg-primary-soft' },
              { label: 'Team size', value: kpis.employee_count, icon: Users, to: '/hr/employees', tone: 'text-gold bg-gold-soft' },
            ].map((item) => (
              <Link key={item.label} to={item.to} className="rounded-2xl border border-line bg-surface-2/50 p-3.5 transition hover:-translate-y-0.5 hover:bg-surface-2">
                <span className={`inline-flex h-8 w-8 items-center justify-center rounded-xl ${item.tone}`}>
                  <item.icon size={15} />
                </span>
                <p className="display mt-2.5 text-xl font-semibold text-ink">{num(item.value)}</p>
                <p className="mt-0.5 text-[10px] font-semibold text-muted">{item.label}</p>
              </Link>
            ))}
          </div>
          <div className="border-t border-line px-5 py-4">
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-muted">Lead → deal conversion</span>
              <span className="font-bold text-ink">{leadToDeal}%</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2">
              <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(leadToDeal, 100)}%` }} />
            </div>
            <p className="mt-2 text-[10px] text-muted">{kpis.lead_count} leads · {kpis.open_deals} open deals</p>
          </div>
        </SectionCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <SectionCard className="lg:col-span-2" title="Recent activity" description="The audit trail, in plain language." action={<span className="inline-flex items-center gap-1 text-[10px] font-semibold text-muted"><Clock size={11} /> live</span>}>
          <ActivityList items={activity} />
        </SectionCard>
        <InsightsPanel insights={insights} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[
          { label: 'Record a sale', to: '/sales/orders', icon: ShoppingBag },
          { label: 'Raise an invoice', to: '/finance/invoices', icon: FileText },
          { label: 'Receive stock', to: '/procurement/purchase-orders', icon: Package },
          { label: 'Review reports', to: '/finance/reports', icon: TrendingUp },
        ].map((action) => (
          <Link key={action.label} to={action.to} className="card flex items-center gap-3 p-4 transition hover:-translate-y-0.5 hover:border-primary/30">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-primary-soft text-primary">
              <action.icon size={16} />
            </span>
            <span className="flex-1 text-xs font-bold text-ink">{action.label}</span>
            <ArrowUpRight size={14} className="text-muted" />
          </Link>
        ))}
      </div>

      <div className="flex items-center justify-between rounded-2xl border border-dashed border-line bg-surface-2/50 px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-gold-soft text-gold"><Target size={16} /></span>
          <div>
            <p className="text-xs font-bold text-ink">Close the loop</p>
            <p className="text-[11px] text-muted">Ask the assistant what needs attention this week.</p>
          </div>
        </div>
        <Link to="/assistant" className="inline-flex items-center gap-1 text-xs font-bold text-primary hover:underline">
          Ask now <ArrowRight size={13} />
        </Link>
      </div>
    </div>
  )
}
