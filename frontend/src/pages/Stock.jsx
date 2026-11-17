import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Boxes, CircleDollarSign, Package, Plus } from 'lucide-react'
import { api, apiErrorMessage } from '../lib/api'
import { cn, money, num } from '../lib/format'
import { EmptyState, KpiCard, PageHeader, SearchInput } from '../components/ui'

export default function Stock() {
  const [levels, setLevels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [lowOnly, setLowOnly] = useState(false)

  useEffect(() => {
    api
      .get('/inventory/stock-levels')
      .then(({ data }) => setLevels(data))
      .catch((requestError) => setError(apiErrorMessage(requestError, 'Could not load stock levels.')))
      .finally(() => setLoading(false))
  }, [])

  const stats = useMemo(() => {
    const onHand = levels.reduce((sum, row) => sum + Number(row.on_hand ?? 0), 0)
    const value = levels.reduce((sum, row) => sum + Number(row.stock_value ?? 0), 0)
    const low = levels.filter((row) => row.below_reorder).length
    return { onHand, value, low }
  }, [levels])

  const filtered = useMemo(() => {
    const needle = search.toLowerCase()
    return levels.filter((row) => {
      if (lowOnly && !row.below_reorder) return false
      if (!needle) return true
      return `${row.sku} ${row.name}`.toLowerCase().includes(needle)
    })
  }, [levels, lowOnly, search])

  if (error) {
    return <EmptyState title="Stock unavailable" description={error} />
  }

  return (
    <>
      <PageHeader
        eyebrow="Inventory"
        title="Stock on hand"
        description="Live quantities and valuation, with reorder alerts surfaced first."
        actions={
          <Link to="/inventory/stock-moves" className="btn-primary">
            <Plus size={16} /> Record movement
          </Link>
        }
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4 stagger">
        <KpiCard label="Products tracked" value={num(levels.length)} hint="active SKUs" icon={Package} tone="primary" />
        <KpiCard label="Units on hand" value={num(stats.onHand, 2)} hint="across all warehouses" icon={Boxes} tone="sky" />
        <KpiCard label="Stock value" value={money(stats.value)} hint="at cost" icon={CircleDollarSign} tone="gold" />
        <KpiCard label="Below reorder" value={num(stats.low)} hint="need replenishment" icon={AlertTriangle} tone="accent" />
      </div>

      <div className="card overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <SearchInput className="w-full sm:w-72" value={search} onChange={setSearch} placeholder="Search SKU or product…" />
          <button
            type="button"
            onClick={() => setLowOnly((value) => !value)}
            className={cn(
              'inline-flex items-center gap-2 self-start rounded-xl border px-3.5 py-2.5 text-xs font-bold transition sm:self-auto',
              lowOnly ? 'border-accent bg-accent-soft text-accent' : 'border-line bg-surface text-ink-soft hover:bg-surface-2',
            )}
          >
            <AlertTriangle size={14} />
            Below reorder only
          </button>
        </div>

        {loading ? (
          <div className="shimmer m-5 h-64 rounded-xl" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse">
              <thead className="border-b border-line bg-surface-2/70">
                <tr>
                  <th className="th">Product</th>
                  <th className="th text-right">On hand</th>
                  <th className="th text-right">Reorder level</th>
                  <th className="th">Coverage</th>
                  <th className="th text-right">Unit cost</th>
                  <th className="th text-right">Stock value</th>
                  <th className="th">Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => {
                  const onHand = Number(row.on_hand ?? 0)
                  const reorder = Number(row.reorder_level ?? 0)
                  const coverage = reorder > 0 ? Math.min((onHand / (reorder * 2)) * 100, 100) : 100
                  return (
                    <tr key={row.product_id} className="border-b border-line/70 transition last:border-0 hover:bg-surface-2/60">
                      <td className="td">
                        <p className="font-semibold text-ink">{row.name}</p>
                        <p className="mt-0.5 text-[11px] text-muted">{row.sku}</p>
                      </td>
                      <td className="td text-right font-bold tabular-nums text-ink">{num(onHand, 2)}</td>
                      <td className="td text-right tabular-nums text-muted">{num(reorder, 2)}</td>
                      <td className="td">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-2">
                            <div
                              className={cn('h-full rounded-full', row.below_reorder ? 'bg-accent' : 'bg-primary')}
                              style={{ width: `${coverage}%` }}
                            />
                          </div>
                          <span className="text-[10px] font-semibold text-muted">{Math.round(coverage)}%</span>
                        </div>
                      </td>
                      <td className="td text-right tabular-nums">{money(row.unit_cost)}</td>
                      <td className="td text-right font-semibold tabular-nums text-ink">{money(row.stock_value)}</td>
                      <td className="td">
                        {row.below_reorder ? (
                          <span className="badge bg-accent-soft text-accent ring-accent/20">Reorder</span>
                        ) : (
                          <span className="badge bg-emerald-50 text-emerald-700 ring-emerald-200">Healthy</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {!filtered.length && (
              <EmptyState compact icon={Package} title="No matching stock" description="Try a different filter or search term." />
            )}
          </div>
        )}
      </div>
    </>
  )
}
