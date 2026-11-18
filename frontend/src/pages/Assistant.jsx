import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BarChart3,
  Bot,
  CircleDollarSign,
  FolderKanban,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  TriangleAlert,
  User,
} from 'lucide-react'
import { api, apiErrorMessage } from '../lib/api'
import { cn, num, titleCase } from '../lib/format'
import { fetchLookup } from '../lib/lookups'
import { PROJECT_ASSISTANT_PROMPTS, scopedProjectQuestion } from '../lib/project-helpers'
import { useAuth } from '../store/auth'
import { toast } from '../store/toast'
import { RemoteSelect } from '../components/Form'
import { PageHeader, Spinner } from '../components/ui'

const STARTERS = [
  'How is revenue trending this quarter?',
  'Which invoices are overdue and by how much?',
  'What products should I restock first?',
  'Summarise the sales pipeline by stage.',
  'How many employees are on leave this month?',
]

const INTENT_LABELS = {
  project_critical_path: 'Critical path',
  project_unbilled: 'Unbilled work',
  project_allocation: 'Resource allocation',
  project_status: 'Status report',
  project_baseline: 'Baseline variance',
  project_blocked: 'Blocked work',
  project_flow: 'Flow metrics',
  project_risk: 'Delivery risk',
  projects: 'Project delivery',
}

const SEVERITY = {
  critical: { cls: 'border-rose-200 bg-rose-50 text-rose-700', Icon: ShieldAlert },
  warning: { cls: 'border-amber-200 bg-amber-50 text-amber-700', Icon: TriangleAlert },
  opportunity: { cls: 'border-emerald-200 bg-emerald-50 text-emerald-700', Icon: TrendingUp },
  info: { cls: 'border-sky-200 bg-sky-50 text-sky-700', Icon: CircleDollarSign },
}

function DataChips({ data }) {
  if (!data || typeof data !== 'object') return null
  const entries = Object.entries(data).filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value)).slice(0, 4)
  if (!entries.length) return null
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {entries.map(([key, value]) => (
        <span key={key} className="rounded-lg border border-line bg-surface px-2.5 py-1 text-[10px] font-semibold text-ink-soft">
          {key.replace(/_/g, ' ')}: <span className="font-bold text-ink">{typeof value === 'number' ? num(value, 2) : String(value)}</span>
        </span>
      ))}
    </div>
  )
}

function Citations({ items }) {
  if (!Array.isArray(items) || items.length === 0) return null
  return (
    <div className="mt-3 border-t border-line pt-2">
      <p className="text-[9px] font-bold uppercase tracking-wider text-muted">Sources</p>
      <div className="mt-1.5 flex flex-wrap gap-1.5">
        {items.slice(0, 6).map((item, index) => {
          const projectId = item.project_id ?? item.projectId
          const workItemId = item.work_item_id ?? item.workItemId
          const label = projectId
            ? `Project ${String(projectId).slice(0, 8)}`
            : workItemId
              ? `Work item ${String(workItemId).slice(0, 8)}`
              : titleCase(item.status_update_id ? 'status update' : Object.keys(item)[0] ?? 'record')
          const to = projectId
            ? `/projects/projects/${projectId}`
            : workItemId
              ? `/projects/work-items?work_item_id=${workItemId}`
              : '/projects/reports'
          return (
            <Link key={`${label}-${index}`} to={to} className="rounded-md bg-surface-2 px-2 py-1 text-[10px] font-semibold text-ink-soft hover:text-primary">
              {label}
            </Link>
          )
        })}
      </div>
    </div>
  )
}

export default function Assistant() {
  const can = useAuth((state) => state.can)
  const canUse = can('ai.assistant.use')
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'Hello — I am Hive, your ERP copilot. Ask me about revenue, receivables, inventory, pipeline or people, and I will query the live workspace for you.',
      intent: 'welcome',
      suggestions: STARTERS.slice(0, 3),
    },
  ])
  const [insights, setInsights] = useState([])
  const [projects, setProjects] = useState([])
  const [projectId, setProjectId] = useState('')
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [loadingInsights, setLoadingInsights] = useState(true)
  const scrollRef = useRef(null)

  const loadInsights = async () => {
    setLoadingInsights(true)
    try {
      const { data } = await api.get('/ai/insights')
      setInsights(data.insights ?? [])
    } catch (error) {
      toast.error('Could not load insights', apiErrorMessage(error))
    } finally {
      setLoadingInsights(false)
    }
  }

  useEffect(() => {
    loadInsights()
    fetchLookup('projects')
      .then(setProjects)
      .catch(() => setProjects([]))
  }, [])

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages, asking])

  const ask = async (text) => {
    const selectedProject = projects.find((project) => project.value === projectId)?.raw
    const prompt = scopedProjectQuestion(text ?? question, selectedProject)
    if (!prompt || asking) return
    setMessages((current) => [...current, { role: 'user', text: prompt, projectId }])
    setQuestion('')
    setAsking(true)
    try {
      const { data } = await api.post('/ai/ask', { question: prompt })
      setMessages((current) => [
        ...current,
        { role: 'assistant', text: data.answer, intent: data.intent, data: data.data, suggestions: data.suggestions },
      ])
    } catch (error) {
      setMessages((current) => [...current, { role: 'assistant', text: apiErrorMessage(error, 'I could not answer that just now.'), intent: 'error' }])
    } finally {
      setAsking(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Intelligence"
        title="Hive assistant"
        description="Read-only answers grounded in live ERP records. Project questions are scoped to the selected project; financial fields follow your access."
        actions={
          <>
            <div className="w-56">
              <RemoteSelect lookup="projects" value={projectId} onChange={setProjectId} placeholder="All projects" />
            </div>
            <Link to="/projects/reports?report=ai_governance" className="btn-secondary">
              <BarChart3 size={15} /> AI governance
            </Link>
            <button type="button" className="btn-secondary" onClick={loadInsights} disabled={loadingInsights}>
              <RefreshCw size={15} className={cn(loadingInsights && 'animate-spin')} /> Refresh signals
            </button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-line bg-surface px-4 py-2.5 text-[11px] text-ink-soft">
        <ShieldAlert size={14} className="text-accent" />
        <span className="font-semibold">Read-only by design:</span>
        <span>Hive never closes work, approves time, posts invoices, changes baselines, books capacity or sends messages. Agentic changes require a separate human-reviewed action.</span>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.5fr_0.8fr]">
        <div className="card flex min-h-[600px] flex-col overflow-hidden">
          <div className="flex items-center gap-3 border-b border-line px-5 py-4">
            <span className="relative inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-forest">
              <Sparkles size={18} />
              <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-surface bg-emerald-400" />
            </span>
            <div>
              <h2 className="text-sm font-bold text-ink">Hive</h2>
              <p className="text-[10px] font-semibold text-emerald-600">Online · reading live data</p>
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-5 overflow-y-auto bg-canvas/40 px-5 py-6">
            {messages.map((message, index) => (
              <div key={index} className={cn('flex gap-3', message.role === 'user' && 'flex-row-reverse')}>
                <span className={cn('inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl', message.role === 'user' ? 'bg-surface-2 text-ink-soft ring-1 ring-line' : 'bg-primary text-forest')}>
                  {message.role === 'user' ? <User size={14} /> : <Bot size={15} />}
                </span>
                <div className={cn('max-w-[82%]', message.role === 'user' && 'text-right')}>
                  <div
                    className={cn(
                      'inline-block rounded-2xl px-4 py-3 text-left',
                      message.role === 'user' ? 'bg-primary text-forest' : 'border border-line bg-surface shadow-sm',
                    )}
                  >
                    {message.role === 'assistant' && message.intent && message.intent !== 'welcome' && (
                      <span className="mb-1.5 block text-[9px] font-bold uppercase tracking-wider text-primary/70">
                        {INTENT_LABELS[message.intent] ?? titleCase(message.intent.replace(/_/g, ' '))}
                      </span>
                    )}
                    <p className={cn('whitespace-pre-wrap text-xs leading-relaxed', message.role === 'user' ? 'text-forest' : 'text-ink-soft')}>{message.text}</p>
                    {message.role === 'assistant' && message.data?.financials_masked && (
                      <p className="mt-2 text-[10px] font-semibold text-amber-700">Financial fields were redacted because you do not have projects.finance.read.</p>
                    )}
                    {message.role === 'assistant' && <DataChips data={message.data} />}
                    {message.role === 'assistant' && <Citations items={message.data?.citations} />}
                  </div>
                  {message.suggestions?.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      {message.suggestions.map((suggestion) => (
                        <button
                          key={suggestion}
                          type="button"
                          onClick={() => ask(suggestion)}
                          className="rounded-full border border-line bg-surface px-3 py-1 text-[10px] font-semibold text-ink-soft transition hover:border-primary/30 hover:text-primary"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {asking && (
              <div className="flex gap-3">
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-forest"><Bot size={15} /></span>
                <div className="inline-flex items-center gap-1.5 rounded-2xl border border-line bg-surface px-4 py-3.5">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/50 [animation-delay:-0.3s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/50 [animation-delay:-0.15s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/50" />
                </div>
              </div>
            )}
          </div>

          <form
            onSubmit={(event) => {
              event.preventDefault()
              ask()
            }}
            className="border-t border-line bg-surface px-4 py-3"
          >
            <div className="flex items-end gap-2">
              <textarea
                className="input min-h-[48px] flex-1 resize-none py-3 text-xs"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault()
                    ask()
                  }
                }}
                placeholder={canUse ? 'Ask Hive anything about your business…' : 'You do not have assistant access'}
                disabled={!canUse}
                rows={1}
              />
              <button type="submit" className="btn-primary h-10 w-10 shrink-0 px-0" disabled={asking || !question.trim() || !canUse}>
                {asking ? <Spinner className="h-4 w-4" /> : <Send size={15} />}
              </button>
            </div>
            {messages.length <= 1 && (
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {STARTERS.map((starter) => (
                  <button key={starter} type="button" onClick={() => ask(starter)} className="rounded-full bg-surface-2 px-3 py-1 text-[10px] font-semibold text-muted transition hover:text-primary">
                    {starter}
                  </button>
                ))}
              </div>
            )}
          </form>
        </div>

        <div className="space-y-4">
          <section className="card overflow-hidden">
            <div className="border-b border-line px-5 py-4">
              <h2 className="text-sm font-bold text-ink">Signals right now</h2>
              <p className="mt-0.5 text-xs text-muted">Generated from your current numbers.</p>
            </div>
            <div className="space-y-2.5 p-4">
              {loadingInsights && Array.from({ length: 3 }).map((_, index) => <div key={index} className="shimmer h-20 rounded-xl" />)}
              {!loadingInsights && insights.length === 0 && <p className="py-6 text-center text-xs text-muted">No signals — everything looks steady.</p>}
              {insights.map((insight) => {
                const tone = SEVERITY[insight.severity] ?? SEVERITY.info
                return (
                  <div key={insight.title} className={cn('rounded-xl border p-3.5', tone.cls)}>
                    <div className="flex items-center gap-2">
                      <tone.Icon size={14} />
                      <p className="text-[11px] font-bold">{insight.title}</p>
                    </div>
                    <p className="mt-1.5 text-[10px] leading-relaxed opacity-90">{insight.detail}</p>
                    <p className="mt-2 text-[10px] font-bold uppercase tracking-wider opacity-70">{insight.metric}</p>
                  </div>
                )
              })}
            </div>
          </section>

          <section className="card overflow-hidden">
            <div className="border-b border-line px-5 py-4">
              <h2 className="text-sm font-bold text-ink">Project questions</h2>
              <p className="mt-0.5 text-xs text-muted">
                {projectId ? `Scoped to ${projects.find((project) => project.value === projectId)?.label ?? projectId}.` : 'Select a project above to scope the answer.'}
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5 p-4">
              {PROJECT_ASSISTANT_PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => ask(prompt)}
                  disabled={asking || !canUse}
                  className="rounded-full border border-line bg-surface px-3 py-1 text-left text-[10px] font-semibold text-ink-soft transition hover:border-primary/30 hover:text-primary disabled:opacity-50"
                >
                  <FolderKanban size={10} className="mr-1 inline" />
                  {prompt}
                </button>
              ))}
            </div>
          </section>

          <section className="card overflow-hidden">
            <div className="border-b border-line px-5 py-4">
              <h2 className="text-sm font-bold text-ink">Jump to the source</h2>
              <p className="mt-0.5 text-xs text-muted">Verify any answer in the underlying module.</p>
            </div>
            <div className="divide-y divide-line">
              {[
                { to: '/finance/reports', label: 'Financial reports', hint: 'Profit, receivables, cash' },
                { to: '/inventory/stock', label: 'Stock on hand', hint: 'Coverage and reorder' },
                { to: '/crm/deals', label: 'Pipeline', hint: 'Deals by stage' },
                { to: '/sales/orders', label: 'Sales orders', hint: 'Fulfilment queue' },
                { to: '/projects/reports', label: 'Project reports', hint: 'Delivery and money analytics' },
                { to: '/projects/ai-signals', label: 'AI review queue', hint: 'Signals, features and review state' },
              ].map((item) => (
                <Link key={item.to} to={item.to} className="flex items-center justify-between px-5 py-3 transition hover:bg-surface-2/70">
                  <div>
                    <p className="text-xs font-bold text-ink">{item.label}</p>
                    <p className="text-[10px] text-muted">{item.hint}</p>
                  </div>
                  <ArrowRight size={14} className="text-muted" />
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>
    </>
  )
}
