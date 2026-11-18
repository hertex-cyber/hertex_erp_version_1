import { useEffect, useMemo, useState } from 'react'
import {
  Banknote,
  Calculator,
  CheckCircle2,
  CreditCard,
  Landmark,
  Minus,
  Monitor,
  Plus,
  Power,
  Receipt,
  RefreshCw,
  Search,
  Smartphone,
  Trash2,
  Wallet,
} from 'lucide-react'
import { api, apiErrorMessage } from '../lib/api'
import { cn, dateTimeLabel, money, num } from '../lib/format'
import { useAuth } from '../store/auth'
import { toast } from '../store/toast'
import { EmptyState, Modal, PageHeader, SectionCard, Spinner } from '../components/ui'

const PAYMENT_METHODS = [
  { key: 'cash', label: 'Cash', icon: Banknote },
  { key: 'card', label: 'Card', icon: CreditCard },
  { key: 'upi', label: 'UPI', icon: Smartphone },
  { key: 'bank', label: 'Bank', icon: Landmark },
]

function ProductCard({ product, onAdd }) {
  return (
    <button
      type="button"
      onClick={() => onAdd(product)}
      className="group flex flex-col rounded-2xl border border-line bg-surface p-3.5 text-left transition hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-[var(--shadow-card)]"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-primary-soft text-primary">
          <Receipt size={16} />
        </span>
        <span className="badge bg-surface-2 text-muted ring-line">{num(product.tax_rate, 1)}% GST</span>
      </div>
      <p className="mt-3 line-clamp-2 min-h-[2.5rem] text-xs font-bold leading-snug text-ink">{product.name}</p>
      <p className="mt-0.5 text-[10px] text-muted">{product.sku} · {product.uom}</p>
      <div className="mt-3 flex items-center justify-between">
        <span className="font-bold tabular-nums text-ink">{money(product.sale_price)}</span>
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-primary-soft text-primary transition group-hover:bg-primary group-hover:text-forest">
          <Plus size={14} />
        </span>
      </div>
    </button>
  )
}

export default function Pos() {
  const can = useAuth((state) => state.can)
  const [products, setProducts] = useState([])
  const [customers, setCustomers] = useState([])
  const [sessions, setSessions] = useState([])
  const [recentSales, setRecentSales] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [cart, setCart] = useState([])
  const [customerId, setCustomerId] = useState('')
  const [payment, setPayment] = useState('cash')
  const [checkingOut, setCheckingOut] = useState(false)
  const [sessionModal, setSessionModal] = useState(false)
  const [sessionForm, setSessionForm] = useState({ terminal_name: 'Main counter', opening_cash: '0' })
  const [closingCash, setClosingCash] = useState('')
  const [closing, setClosing] = useState(false)

  const openSession = sessions.find((session) => session.status === 'open')
  const canCheckout = can('pos.sale.checkout')

  const loadData = async () => {
    setLoading(true)
    try {
      const [productResponse, sessionResponse, customerResponse, salesResponse] = await Promise.all([
        api.get('/inventory/products', { params: { size: 200 } }),
        api.get('/pos/sessions', { params: { size: 50 } }),
        api.get('/sales/customers', { params: { size: 200 } }),
        api.get('/pos/sales', { params: { size: 8 } }),
      ])
      setProducts(productResponse.data.items ?? [])
      setSessions(sessionResponse.data.items ?? [])
      setCustomers(customerResponse.data.items ?? [])
      setRecentSales(salesResponse.data.items ?? [])
    } catch (error) {
      toast.error('Could not load POS', apiErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const filtered = useMemo(() => {
    const needle = search.toLowerCase()
    if (!needle) return products
    return products.filter((product) => `${product.name} ${product.sku} ${product.barcode ?? ''}`.toLowerCase().includes(needle))
  }, [products, search])

  const totals = useMemo(() => {
    let subtotal = 0
    let tax = 0
    for (const line of cart) {
      const base = Number(line.product.sale_price) * line.quantity
      subtotal += base
      tax += (base * Number(line.product.tax_rate ?? 0)) / 100
    }
    return { subtotal, tax, total: subtotal + tax }
  }, [cart])

  const addToCart = (product) => {
    setCart((current) => {
      const existing = current.find((line) => line.product.id === product.id)
      if (existing) {
        return current.map((line) => (line.product.id === product.id ? { ...line, quantity: line.quantity + 1 } : line))
      }
      return [...current, { product, quantity: 1 }]
    })
  }

  const setQty = (productId, quantity) => {
    if (quantity <= 0) {
      setCart((current) => current.filter((line) => line.product.id !== productId))
      return
    }
    setCart((current) => current.map((line) => (line.product.id === productId ? { ...line, quantity } : line)))
  }

  const checkout = async () => {
    if (!cart.length) return
    setCheckingOut(true)
    try {
      const { data } = await api.post('/pos/checkout', {
        session_id: openSession?.id ?? null,
        customer_id: customerId || null,
        payment_method: payment,
        lines: cart.map((line) => ({
          product_id: line.product.id,
          quantity: line.quantity,
          unit_price: line.product.sale_price,
        })),
      })
      toast.success('Sale completed', `${data.sale_number} · ${money(data.total)} collected.`)
      setCart([])
      setCustomerId('')
      const salesResponse = await api.get('/pos/sales', { params: { size: 8 } })
      setRecentSales(salesResponse.data.items ?? [])
    } catch (error) {
      toast.error('Checkout failed', apiErrorMessage(error))
    } finally {
      setCheckingOut(false)
    }
  }

  const startSession = async (event) => {
    event.preventDefault()
    try {
      await api.post('/pos/sessions', {
        terminal_name: sessionForm.terminal_name,
        opening_cash: sessionForm.opening_cash || 0,
      })
      toast.success('Terminal opened', 'The session is ready for sales.')
      setSessionModal(false)
      setSessionForm({ terminal_name: 'Main counter', opening_cash: '0' })
      await loadData()
    } catch (error) {
      toast.error('Could not open terminal', apiErrorMessage(error))
    }
  }

  const closeSession = async () => {
    if (!openSession) return
    setClosing(true)
    try {
      await api.post(`/pos/sessions/${openSession.id}/close`, null, { params: { closing_cash: closingCash || 0 } })
      toast.success('Terminal closed', 'The cash drawer has been reconciled.')
      setClosingCash('')
      await loadData()
    } catch (error) {
      toast.error('Could not close terminal', apiErrorMessage(error))
    } finally {
      setClosing(false)
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Point of sale"
        title="Counter"
        description="Sell in person, take payment, and reconcile the drawer without leaving the workspace."
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={loadData}>
              <RefreshCw size={15} className={cn(loading && 'animate-spin')} /> Refresh
            </button>
            {openSession ? (
              <button type="button" className="btn-secondary" onClick={closeSession} disabled={closing}>
                {closing ? <Spinner className="h-4 w-4" /> : <Power size={15} />} Close terminal
              </button>
            ) : (
              <button type="button" className="btn-primary" onClick={() => setSessionModal(true)}>
                <Monitor size={15} /> Open terminal
              </button>
            )}
          </>
        }
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        <div className="card flex items-center gap-3 p-4">
          <span className={cn('inline-flex h-10 w-10 items-center justify-center rounded-xl', openSession ? 'bg-emerald-50 text-emerald-700' : 'bg-surface-2 text-muted')}>
            <Monitor size={17} />
          </span>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted">Terminal</p>
            <p className="text-sm font-bold text-ink">{openSession?.terminal_name ?? 'No open session'}</p>
          </div>
        </div>
        <div className="card flex items-center gap-3 p-4">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-gold-soft text-gold">
            <Wallet size={17} />
          </span>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted">Opening cash</p>
            <p className="text-sm font-bold text-ink">{money(openSession?.opening_cash ?? 0)}</p>
          </div>
        </div>
        <div className="card flex items-center gap-3 p-4">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary-soft text-primary">
            <Receipt size={17} />
          </span>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-muted">Sales this session</p>
            <p className="text-sm font-bold text-ink">{num(recentSales.filter((sale) => sale.session_id === openSession?.id).length)} recent</p>
          </div>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.55fr_0.85fr]">
        <div>
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-xs">
              <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
              <input className="input pl-10" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Scan or search products…" />
            </div>
            <p className="text-xs text-muted"><span className="font-bold text-ink">{filtered.length}</span> products available</p>
          </div>

          {loading ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
              {Array.from({ length: 8 }).map((_, index) => <div key={index} className="shimmer h-40 rounded-2xl" />)}
            </div>
          ) : filtered.length ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
              {filtered.map((product) => <ProductCard key={product.id} product={product} onAdd={addToCart} />)}
            </div>
          ) : (
            <EmptyState title="No products found" description="Adjust the search or add products to the catalogue." />
          )}

          <SectionCard className="mt-5" title="Recent sales" description="Latest transactions from this workspace.">
            {recentSales.length ? (
              <div className="divide-y divide-line">
                {recentSales.map((sale) => (
                  <div key={sale.id} className="flex items-center gap-3 px-5 py-3">
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700"><CheckCircle2 size={14} /></span>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-bold text-ink">{sale.sale_number}</p>
                      <p className="text-[10px] text-muted">{dateTimeLabel(sale.created_at)} · {sale.payment_method} · {(sale.lines ?? []).length} lines</p>
                    </div>
                    <span className="font-bold tabular-nums text-ink">{money(sale.total)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState compact icon={Receipt} title="No sales yet" description="Completed checkouts will appear here." />
            )}
          </SectionCard>
        </div>

        <div className="xl:sticky xl:top-[92px] xl:self-start">
          <div className="card overflow-hidden">
            <div className="flex items-center justify-between border-b border-line px-5 py-4">
              <div className="flex items-center gap-2">
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-primary-soft text-primary"><Calculator size={15} /></span>
                <div>
                  <h2 className="text-sm font-bold text-ink">Current sale</h2>
                  <p className="text-[10px] text-muted">{cart.length} line{cart.length === 1 ? '' : 's'}</p>
                </div>
              </div>
              {cart.length > 0 && (
                <button type="button" className="text-[11px] font-bold text-rose-600 hover:underline" onClick={() => setCart([])}>Clear</button>
              )}
            </div>

            <div className="max-h-[330px] overflow-y-auto">
              {cart.length === 0 ? (
                <EmptyState compact icon={Receipt} title="Cart is empty" description="Tap a product to start a sale." />
              ) : (
                <div className="divide-y divide-line">
                  {cart.map((line) => (
                    <div key={line.product.id} className="px-4 py-3">
                      <div className="flex items-start gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs font-bold text-ink">{line.product.name}</p>
                          <p className="text-[10px] text-muted">{money(line.product.sale_price)} · {num(line.product.tax_rate, 1)}% GST</p>
                        </div>
                        <button type="button" className="text-muted hover:text-rose-600" onClick={() => setQty(line.product.id, 0)} aria-label="Remove">
                          <Trash2 size={13} />
                        </button>
                      </div>
                      <div className="mt-2 flex items-center justify-between">
                        <div className="inline-flex items-center rounded-lg border border-line">
                          <button type="button" className="inline-flex h-7 w-7 items-center justify-center text-muted hover:text-ink" onClick={() => setQty(line.product.id, line.quantity - 1)}>
                            <Minus size={12} />
                          </button>
                          <span className="w-8 text-center text-xs font-bold text-ink">{line.quantity}</span>
                          <button type="button" className="inline-flex h-7 w-7 items-center justify-center text-muted hover:text-ink" onClick={() => setQty(line.product.id, line.quantity + 1)}>
                            <Plus size={12} />
                          </button>
                        </div>
                        <span className="text-xs font-bold tabular-nums text-ink">{money(Number(line.product.sale_price) * line.quantity)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="border-t border-line px-5 py-4">
              <label className="label">Customer (optional)</label>
              <select className="input mb-3 py-2 text-xs" value={customerId} onChange={(event) => setCustomerId(event.target.value)}>
                <option value="">Walk-in customer</option>
                {customers.map((customer) => (
                  <option key={customer.id} value={customer.id}>{customer.name}</option>
                ))}
              </select>

              <div className="mb-3 grid grid-cols-4 gap-1.5">
                {PAYMENT_METHODS.map((method) => (
                  <button
                    key={method.key}
                    type="button"
                    onClick={() => setPayment(method.key)}
                    className={cn(
                      'flex flex-col items-center gap-1 rounded-xl border px-1 py-2 text-[10px] font-bold transition',
                      payment === method.key ? 'border-primary bg-primary text-forest' : 'border-line bg-surface text-muted hover:bg-surface-2 hover:text-ink',
                    )}
                  >
                    <method.icon size={14} />
                    {method.label}
                  </button>
                ))}
              </div>

              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between text-muted"><span>Subtotal</span><span className="tabular-nums">{money(totals.subtotal)}</span></div>
                <div className="flex justify-between text-muted"><span>Tax</span><span className="tabular-nums">{money(totals.tax)}</span></div>
                <div className="flex items-baseline justify-between border-t border-dashed border-line pt-2">
                  <span className="text-sm font-bold text-ink">Total</span>
                  <span className="display text-2xl font-semibold text-ink">{money(totals.total)}</span>
                </div>
              </div>

              <button type="button" className="btn-primary mt-4 w-full py-3" disabled={!cart.length || checkingOut || !canCheckout} onClick={checkout}>
                {checkingOut ? <Spinner className="h-4 w-4" /> : <CheckCircle2 size={16} />}
                {canCheckout ? 'Complete sale' : 'No checkout permission'}
              </button>
              {!openSession && <p className="mt-2 text-center text-[10px] font-semibold text-amber-700">Open a terminal session to keep sales grouped.</p>}
            </div>
          </div>
        </div>
      </div>

      <Modal
        open={sessionModal}
        onClose={() => setSessionModal(false)}
        title="Open terminal"
        description="Start a cash session before taking counter sales."
        size="sm"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setSessionModal(false)}>Cancel</button>
            <button type="button" className="btn-primary" onClick={startSession}>Open terminal</button>
          </>
        }
      >
        <form onSubmit={startSession} className="space-y-4">
          <div>
            <label className="label">Terminal name</label>
            <input className="input" value={sessionForm.terminal_name} onChange={(event) => setSessionForm((current) => ({ ...current, terminal_name: event.target.value }))} required />
          </div>
          <div>
            <label className="label">Opening cash</label>
            <input className="input" type="number" step="any" value={sessionForm.opening_cash} onChange={(event) => setSessionForm((current) => ({ ...current, opening_cash: event.target.value }))} />
          </div>
        </form>
      </Modal>

      {openSession && (
        <div className="fixed bottom-5 right-5 z-20 hidden items-center gap-2 rounded-2xl border border-line bg-surface p-2 shadow-[var(--shadow-float)] lg:flex">
          <span className="px-2 text-[10px] font-bold uppercase tracking-wider text-muted">Closing cash</span>
          <input className="input w-28 py-1.5 text-xs" type="number" step="any" value={closingCash} onChange={(event) => setClosingCash(event.target.value)} placeholder="0" />
          <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" onClick={closeSession} disabled={closing}>
            {closing ? <Spinner className="h-3.5 w-3.5" /> : <Power size={13} />} Close
          </button>
        </div>
      )}
    </>
  )
}
