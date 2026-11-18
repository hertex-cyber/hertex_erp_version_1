import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CheckCircle2,
  Clock,
  Inbox,
  LifeBuoy,
  Lock,
  MessageSquare,
  Plus,
  Search,
  Send,
  User,
} from 'lucide-react'
import { api, apiErrorMessage } from '../lib/api'
import { cn, dateTimeLabel, statusClasses, statusTone, titleCase } from '../lib/format'
import { useAuth } from '../store/auth'
import { toast } from '../store/toast'
import { Avatar, EmptyState, Modal, PageHeader, Spinner } from '../components/ui'

const STATUS_TABS = ['all', 'open', 'pending', 'resolved']

const PRIORITY_CLASSES = {
  urgent: 'bg-rose-50 text-rose-700 ring-rose-200',
  high: 'bg-amber-50 text-amber-700 ring-amber-200',
  medium: 'bg-sky-50 text-sky-700 ring-sky-200',
  low: 'bg-stone-100 text-stone-600 ring-stone-200',
}

function TicketRow({ ticket, active, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full border-b border-line/70 px-4 py-3.5 text-left transition last:border-0',
        active ? 'bg-primary-soft/60' : 'hover:bg-surface-2/70',
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-[10px] font-bold uppercase tracking-wider text-muted">{ticket.ticket_number}</p>
        <span className={cn('badge px-2 py-0.5 text-[9px]', PRIORITY_CLASSES[ticket.priority] ?? PRIORITY_CLASSES.low)}>{ticket.priority}</span>
      </div>
      <p className="mt-1 line-clamp-1 text-xs font-bold text-ink">{ticket.subject}</p>
      <p className="mt-0.5 line-clamp-1 text-[10px] text-muted">{ticket.requester_name || ticket.requester_email || 'Unknown requester'}</p>
      <div className="mt-2 flex items-center justify-between">
        <span className={cn('badge px-2 py-0.5 text-[9px]', statusClasses[statusTone(ticket.status)])}>{titleCase(ticket.status)}</span>
        <span className="text-[9px] font-medium text-muted">{dateTimeLabel(ticket.created_at)}</span>
      </div>
    </button>
  )
}

export default function Support() {
  const can = useAuth((state) => state.can)
  const [tickets, setTickets] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeId, setActiveId] = useState(null)
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState('all')
  const [reply, setReply] = useState('')
  const [internal, setInternal] = useState(false)
  const [sending, setSending] = useState(false)
  const [resolving, setResolving] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState({ subject: '', description: '', requester_name: '', requester_email: '', priority: 'medium', channel: 'web' })
  const [creating, setCreating] = useState(false)
  const threadRef = useRef(null)

  const loadTickets = async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/support/tickets', { params: { size: 100 } })
      setTickets(data.items ?? [])
      setActiveId((current) => current ?? data.items?.[0]?.id ?? null)
    } catch (error) {
      toast.error('Could not load tickets', apiErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTickets()
  }, [])

  useEffect(() => {
    if (threadRef.current) threadRef.current.scrollTop = threadRef.current.scrollHeight
  }, [activeId, tickets])

  const filtered = useMemo(() => {
    const needle = search.toLowerCase()
    return tickets.filter((ticket) => {
      if (tab !== 'all' && ticket.status !== tab) return false
      if (!needle) return true
      return `${ticket.ticket_number} ${ticket.subject} ${ticket.requester_name ?? ''}`.toLowerCase().includes(needle)
    })
  }, [tickets, search, tab])

  const active = tickets.find((ticket) => ticket.id === activeId) ?? null

  const counts = useMemo(() => {
    const base = { all: tickets.length, open: 0, pending: 0, resolved: 0 }
    for (const ticket of tickets) base[ticket.status] = (base[ticket.status] ?? 0) + 1
    return base
  }, [tickets])

  const sendReply = async (event) => {
    event.preventDefault()
    if (!active || !reply.trim()) return
    setSending(true)
    try {
      const { data } = await api.post(`/support/tickets/${active.id}/messages`, { body: reply.trim(), is_internal: internal })
      setTickets((current) =>
        current.map((ticket) =>
          ticket.id === active.id ? { ...ticket, messages: [...(ticket.messages ?? []), data], status: ticket.status === 'resolved' && !internal ? 'open' : ticket.status } : ticket,
        ),
      )
      setReply('')
      toast.success(internal ? 'Internal note added' : 'Reply sent')
    } catch (error) {
      toast.error('Could not send reply', apiErrorMessage(error))
    } finally {
      setSending(false)
    }
  }

  const resolve = async () => {
    if (!active) return
    setResolving(true)
    try {
      const { data } = await api.post(`/support/tickets/${active.id}/resolve`)
      setTickets((current) => current.map((ticket) => (ticket.id === active.id ? { ...ticket, ...data, messages: ticket.messages } : ticket)))
      toast.success('Ticket resolved', `${active.ticket_number} marked as resolved.`)
    } catch (error) {
      toast.error('Could not resolve ticket', apiErrorMessage(error))
    } finally {
      setResolving(false)
    }
  }

  const createTicket = async (event) => {
    event.preventDefault()
    setCreating(true)
    try {
      const { data } = await api.post('/support/tickets', createForm)
      setTickets((current) => [data, ...current])
      setActiveId(data.id)
      setCreateOpen(false)
      setCreateForm({ subject: '', description: '', requester_name: '', requester_email: '', priority: 'medium', channel: 'web' })
      toast.success('Ticket created', `${data.ticket_number} is now in the queue.`)
    } catch (error) {
      toast.error('Could not create ticket', apiErrorMessage(error))
    } finally {
      setCreating(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Service desk"
        title="Support inbox"
        description="Every customer conversation in one thread, with priorities, SLAs and internal notes."
        actions={
          <button type="button" className="btn-primary" onClick={() => setCreateOpen(true)} disabled={!can('support.ticket.create')}>
            <Plus size={15} /> New ticket
          </button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <div className="card overflow-hidden">
          <div className="space-y-3 border-b border-line p-4">
            <div className="relative">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input className="input py-2 pl-9 text-xs" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search tickets…" />
            </div>
            <div className="flex gap-1 overflow-x-auto">
              {STATUS_TABS.map((status) => (
                <button
                  key={status}
                  type="button"
                  onClick={() => setTab(status)}
                  className={cn(
                    'flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-bold transition',
                    tab === status ? 'bg-primary text-forest' : 'text-muted hover:bg-surface-2 hover:text-ink',
                  )}
                >
                  {titleCase(status)}
                  <span className={cn('rounded-full px-1.5 text-[9px]', tab === status ? 'bg-white/20' : 'bg-surface-2')}>{counts[status] ?? 0}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="max-h-[calc(100vh-320px)] min-h-[280px] overflow-y-auto">
            {loading ? (
              <div className="space-y-2 p-4">{Array.from({ length: 5 }).map((_, index) => <div key={index} className="shimmer h-16 rounded-xl" />)}</div>
            ) : filtered.length ? (
              filtered.map((ticket) => (
                <TicketRow key={ticket.id} ticket={ticket} active={ticket.id === activeId} onClick={() => setActiveId(ticket.id)} />
              ))
            ) : (
              <EmptyState compact icon={Inbox} title="Inbox zero" description="No tickets match this view." />
            )}
          </div>
        </div>

        <div className="card flex min-h-[520px] flex-col overflow-hidden">
          {!active ? (
            <EmptyState icon={LifeBuoy} title="Select a ticket" description="Pick a conversation from the queue to see the full thread." />
          ) : (
            <>
              <div className="border-b border-line px-5 py-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-muted">{active.ticket_number} · {titleCase(active.channel)}</p>
                    <h2 className="mt-1 text-base font-bold text-ink">{active.subject}</h2>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className={cn('badge px-2 py-0.5 text-[9px]', PRIORITY_CLASSES[active.priority] ?? PRIORITY_CLASSES.low)}>{active.priority}</span>
                      <span className={cn('badge px-2 py-0.5 text-[9px]', statusClasses[statusTone(active.status)])}>{titleCase(active.status)}</span>
                      <span className="inline-flex items-center gap-1 text-[10px] text-muted"><User size={11} /> {active.requester_name || active.requester_email || 'Unknown'}</span>
                      {active.sla_due_at && <span className="inline-flex items-center gap-1 text-[10px] text-muted"><Clock size={11} /> SLA {dateTimeLabel(active.sla_due_at)}</span>}
                    </div>
                  </div>
                  {active.status !== 'resolved' && (
                    <button type="button" className="btn-secondary text-xs" onClick={resolve} disabled={resolving || !can('support.ticket.update')}>
                      {resolving ? <Spinner className="h-3.5 w-3.5" /> : <CheckCircle2 size={14} />} Resolve
                    </button>
                  )}
                </div>
                {active.description && (
                  <p className="mt-3 rounded-xl bg-surface-2/60 px-3.5 py-2.5 text-xs leading-relaxed text-ink-soft">{active.description}</p>
                )}
              </div>

              <div ref={threadRef} className="flex-1 space-y-4 overflow-y-auto bg-canvas/40 px-5 py-5">
                {(active.messages ?? []).length === 0 && (
                  <p className="py-10 text-center text-xs text-muted">No messages yet — send the first reply below.</p>
                )}
                {(active.messages ?? []).map((message) => (
                  <div key={message.id} className={cn('flex gap-2.5', message.is_internal && 'opacity-90')}>
                    <Avatar name={message.author_name} size="sm" />
                    <div className={cn('max-w-[80%] rounded-2xl px-4 py-2.5', message.is_internal ? 'border border-amber-200 bg-amber-50' : 'border border-line bg-surface')}>
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-bold text-ink">{message.author_name || 'Agent'}</span>
                        {message.is_internal && <span className="inline-flex items-center gap-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-700"><Lock size={9} /> Internal</span>}
                        <span className="text-[9px] text-muted">{dateTimeLabel(message.created_at)}</span>
                      </div>
                      <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-ink-soft">{message.body}</p>
                    </div>
                  </div>
                ))}
              </div>

              <form onSubmit={sendReply} className="border-t border-line bg-surface px-4 py-3">
                <div className="flex items-center justify-between pb-2">
                  <div className="inline-flex rounded-lg border border-line p-0.5">
                    <button type="button" onClick={() => setInternal(false)} className={cn('rounded-md px-2.5 py-1 text-[10px] font-bold', !internal ? 'bg-primary text-forest' : 'text-muted')}>Reply</button>
                    <button type="button" onClick={() => setInternal(true)} className={cn('inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[10px] font-bold', internal ? 'bg-amber-500 text-white' : 'text-muted')}>
                      <Lock size={9} /> Note
                    </button>
                  </div>
                  <span className="text-[10px] text-muted">Ctrl + Enter to send</span>
                </div>
                <div className="flex items-end gap-2">
                  <textarea
                    className="input min-h-[64px] flex-1 resize-none py-2 text-xs"
                    value={reply}
                    onChange={(event) => setReply(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) sendReply(event)
                    }}
                    placeholder={internal ? 'Add an internal note — customers will not see this…' : 'Write a reply to the customer…'}
                    required
                  />
                  <button type="submit" className="btn-primary h-9 w-9 shrink-0 px-0" disabled={sending || !reply.trim()}>
                    {sending ? <Spinner className="h-4 w-4" /> : <Send size={15} />}
                  </button>
                </div>
              </form>
            </>
          )}
        </div>
      </div>

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="New support ticket"
        description="Capture a customer issue so it can be triaged and resolved."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setCreateOpen(false)}>Cancel</button>
            <button type="button" className="btn-primary" onClick={createTicket} disabled={creating}>
              {creating ? <Spinner className="h-4 w-4" /> : <Plus size={14} />} Create ticket
            </button>
          </>
        }
      >
        <form onSubmit={createTicket} className="space-y-4">
          <div>
            <label className="label">Subject</label>
            <input className="input" value={createForm.subject} onChange={(event) => setCreateForm((current) => ({ ...current, subject: event.target.value }))} required />
          </div>
          <div>
            <label className="label">Description</label>
            <textarea className="input min-h-[90px] resize-none" value={createForm.description} onChange={(event) => setCreateForm((current) => ({ ...current, description: event.target.value }))} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="label">Requester name</label>
              <input className="input" value={createForm.requester_name} onChange={(event) => setCreateForm((current) => ({ ...current, requester_name: event.target.value }))} />
            </div>
            <div>
              <label className="label">Requester email</label>
              <input className="input" type="email" value={createForm.requester_email} onChange={(event) => setCreateForm((current) => ({ ...current, requester_email: event.target.value }))} />
            </div>
            <div>
              <label className="label">Priority</label>
              <select className="input" value={createForm.priority} onChange={(event) => setCreateForm((current) => ({ ...current, priority: event.target.value }))}>
                {['low', 'medium', 'high', 'urgent'].map((priority) => <option key={priority} value={priority}>{titleCase(priority)}</option>)}
              </select>
            </div>
            <div>
              <label className="label">Channel</label>
              <select className="input" value={createForm.channel} onChange={(event) => setCreateForm((current) => ({ ...current, channel: event.target.value }))}>
                {['web', 'email', 'phone', 'whatsapp', 'chat'].map((channel) => <option key={channel} value={channel}>{titleCase(channel)}</option>)}
              </select>
            </div>
          </div>
        </form>
      </Modal>
    </>
  )
}
