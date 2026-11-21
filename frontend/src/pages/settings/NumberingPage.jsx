import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BadgeIndianRupee, Blocks, Eye, Pencil, Plus } from 'lucide-react'
import { api, apiErrorMessage } from '../../lib/api'
import { PageHeader, LoadingBlock, Modal } from '../../components/ui'
import { Status } from '../../components/cells'
import { num } from '../../lib/format'
import { toast } from '../../store/toast'
import SettingsSubnav from '../../components/settings/SettingsSubnav'
import PatternBuilder, { formFromSequence } from '../../components/settings/PatternBuilder'
import SequenceStatusDrawer from '../../components/settings/SequenceStatusDrawer'

function filterForm(form) {
  return {
    key: form.key,
    doc_type: form.doc_type,
    owner_module: form.owner_module,
    pattern: form.pattern,
    prefix: form.prefix,
    suffix: form.suffix,
    padding: Number(form.padding),
    max_length: form.max_length === null || form.max_length === '' ? null : Number(form.max_length),
    irp_safe: Boolean(form.irp_safe),
  }
}

export default function NumberingPage() {
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [module, setModule] = useState('all')
  const [docType, setDocType] = useState('all')
  const [branch, setBranch] = useState('all')
  const [gstin, setGstin] = useState('all')
  const [fiscalYear, setFiscalYear] = useState('all')
  const [scopeTab, setScopeTab] = useState('all')
  const [selected, setSelected] = useState(null)
  const [preview, setPreview] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [statusKey, setStatusKey] = useState(null)
  const [editing, setEditing] = useState(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState(formFromSequence(null))
  const [saving, setSaving] = useState(false)

  async function load() {
    setLoading(true)
    setError('')
    try {
      const response = await api.get('/settings/sequences', { params: { size: 200 } })
      setRows(Array.isArray(response.data?.items) ? response.data.items : [])
    } catch (err) {
      setError(apiErrorMessage(err, 'Number sequences could not be loaded.'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const modules = useMemo(() => ['all', ...Array.from(new Set(rows.map((row) => row.owner_module).filter(Boolean))).sort()], [rows])
  const docTypes = useMemo(() => ['all', ...Array.from(new Set(rows.map((row) => row.doc_type).filter(Boolean))).sort()], [rows])
  const branches = useMemo(() => ['all', ...Array.from(new Set(rows.map((row) => row.branch_id).filter(Boolean)))], [rows])
  const gstins = useMemo(() => ['all', ...Array.from(new Set(rows.map((row) => row.gstin).filter(Boolean)))], [rows])
  const fiscalYears = useMemo(() => ['all', ...Array.from(new Set(rows.map((row) => row.fiscal_year).filter(Boolean))).sort()], [rows])

  const visible = useMemo(() => rows.filter((row) => {
    if (module !== 'all' && row.owner_module !== module) return false
    if (docType !== 'all' && row.doc_type !== docType) return false
    if (branch !== 'all' && row.branch_id !== branch) return false
    if (gstin !== 'all' && row.gstin !== gstin) return false
    if (fiscalYear !== 'all' && row.fiscal_year !== fiscalYear) return false
    if (scopeTab === 'branch' && !row.branch_id) return false
    if (scopeTab === 'gstin' && !row.gstin) return false
    return true
  }), [rows, module, docType, branch, gstin, fiscalYear, scopeTab])

  async function previewSequence(row) {
    setSelected(row)
    setPreview(null)
    setPreviewLoading(true)
    setError('')
    try {
      const response = await api.post(`/settings/sequences/${encodeURIComponent(row.key)}/preview`, {})
      setPreview(response.data)
    } catch (err) {
      setError(apiErrorMessage(err, 'Preview is unavailable for this series.'))
    } finally {
      setPreviewLoading(false)
    }
  }

  function openEditor(row) {
    setEditing(row)
    setForm(formFromSequence(row))
  }

  async function saveEditor() {
    if (!editing) return
    setSaving(true)
    setError('')
    try {
      await api.patch(`/settings/sequences/${encodeURIComponent(editing.key)}`, filterForm(form))
      toast.success('Sequence updated', editing.key)
      setEditing(null)
      await load()
      if (selected?.key === editing.key) await previewSequence({ ...selected })
    } catch (err) {
      setError(apiErrorMessage(err, 'This series could not be updated.'))
    } finally {
      setSaving(false)
    }
  }

  async function createSeries() {
    setSaving(true)
    setError('')
    try {
      await api.post('/settings/sequences', { ...filterForm(form), next_number: 1 })
      toast.success('Series created', form.key)
      setCreating(false)
      await load()
    } catch (err) {
      setError(apiErrorMessage(err, 'The series could not be created.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div data-testid="numbering-page">
      <SettingsSubnav />
      <PageHeader
        eyebrow="Settings"
        title="Number sequences"
        description="Fiscal periods, non-consuming previews and gap-safe allocations for every human-facing document number."
        actions={
          <button type="button" className="btn-primary w-full sm:w-auto" data-testid="create-series" onClick={() => { setForm(formFromSequence(null)); setCreating(true) }}>
            <Plus size={16} /> New series
          </button>
        }
      />

      {error && <p className="card mb-4 p-4 text-sm text-rose-600" data-testid="numbering-error">{error}</p>}

      <div className="card mb-4 p-4">
        <div className="flex flex-wrap gap-1.5" data-testid="numbering-scope-tabs">
          {[
            ['all', 'All series'],
            ['branch', 'Branch series'],
            ['gstin', 'GSTIN series'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${scopeTab === value ? 'bg-primary-soft text-primary' : 'bg-surface-2 text-muted hover:text-ink'}`}
              data-testid={`numbering-tab-${value}`}
              onClick={() => setScopeTab(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
          <select className="input" data-testid="filter-module" value={module} onChange={(event) => setModule(event.target.value)}>
            {modules.map((value) => <option key={value} value={value}>{value === 'all' ? 'All modules' : value}</option>)}
          </select>
          <select className="input" data-testid="filter-doc-type" value={docType} onChange={(event) => setDocType(event.target.value)}>
            {docTypes.map((value) => <option key={value} value={value}>{value === 'all' ? 'All document types' : value}</option>)}
          </select>
          <select className="input" data-testid="filter-branch" value={branch} onChange={(event) => setBranch(event.target.value)}>
            {branches.map((value) => <option key={value} value={value}>{value === 'all' ? 'All branches' : value}</option>)}
          </select>
          <select className="input" data-testid="filter-gstin" value={gstin} onChange={(event) => setGstin(event.target.value)}>
            {gstins.map((value) => <option key={value} value={value}>{value === 'all' ? 'All GSTINs' : value}</option>)}
          </select>
          <select className="input" data-testid="filter-fiscal-year" value={fiscalYear} onChange={(event) => setFiscalYear(event.target.value)}>
            {fiscalYears.map((value) => <option key={value} value={value}>{value === 'all' ? 'All financial years' : value}</option>)}
          </select>
        </div>
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          {loading && <LoadingBlock label="Loading sequences…" />}
          {!loading && (
            <>
              <div className="card hidden overflow-x-auto md:block" data-testid="sequence-table">
                <table className="w-full min-w-[720px] text-sm">
                  <thead className="bg-surface-2 text-left text-xs text-muted">
                    <tr>
                      <th className="th">Series</th><th className="th">Module</th><th className="th">Pattern</th><th className="th">FY</th><th className="th">Next</th><th className="th">Status</th><th className="th">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((row) => (
                      <tr key={row.id} className="border-t" data-testid={`sequence-row-${row.key}`}>
                        <td className="td"><span className="font-semibold text-ink">{row.key}</span><span className="mt-0.5 block text-[10px] text-muted">{row.doc_type}</span></td>
                        <td className="td">{row.owner_module}</td>
                        <td className="td font-mono text-xs">{row.pattern || `${row.prefix}-{row.padding}`}</td>
                        <td className="td">{row.fiscal_year || '—'}</td>
                        <td className="td tabular-nums">{num(row.period_next_number ?? row.next_number)}</td>
                        <td className="td"><Status value={row.locked ? 'locked' : row.status} /></td>
                        <td className="td"><SequenceActions row={row} onPreview={previewSequence} onStatus={setStatusKey} onEdit={openEditor} onBlocks={(key) => navigate(`/settings/numbering/blocks?key=${encodeURIComponent(key)}`)} onGaps={(key) => navigate(`/settings/numbering/gaps?key=${encodeURIComponent(key)}`)} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="space-y-3 md:hidden" data-testid="sequence-cards">
                {visible.map((row) => (
                  <article key={row.id} className="card p-4" data-testid={`sequence-card-${row.key}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0"><p className="break-all font-semibold text-ink">{row.key}</p><p className="text-[11px] text-muted">{row.owner_module} · {row.doc_type}</p></div>
                      <Status value={row.locked ? 'locked' : row.status} />
                    </div>
                    <p className="mt-2 break-all font-mono text-xs text-ink-soft">{row.pattern || `${row.prefix}-{row.padding}`}</p>
                    <p className="mt-1 text-xs text-muted">FY {row.fiscal_year || '—'} · next {num(row.period_next_number ?? row.next_number)}</p>
                    {row.locked && <LockedNote row={row} />}
                    <div className="mt-3"><SequenceActions row={row} onPreview={previewSequence} onStatus={setStatusKey} onEdit={openEditor} onBlocks={(key) => navigate(`/settings/numbering/blocks?key=${encodeURIComponent(key)}`)} onGaps={(key) => navigate(`/settings/numbering/gaps?key=${encodeURIComponent(key)}`)} /></div>
                  </article>
                ))}
              </div>
              {!visible.length && <p className="card p-5 text-sm text-muted">No series match these filters.</p>}
            </>
          )}
        </div>

        <aside className="card w-full p-4 xl:sticky xl:top-24" data-testid="numbering-preview-panel">
          <p className="eyebrow">Non-consuming preview</p>
          <h2 className="mt-1 text-sm font-bold text-ink">{selected?.key || 'Select a series'}</h2>
          {selected?.locked && <div className="mt-3"><LockedNote row={selected} /></div>}
          {previewLoading && <p className="mt-4 text-sm text-muted">Rendering preview…</p>}
          {preview && (
            <div className="mt-4 rounded-xl bg-surface-2 p-4">
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted">Next rendered number</p>
              <p className="mt-2 break-all font-mono text-2xl font-bold text-primary" data-testid="sequence-preview-value" data-preview-value={preview.rendered}>{preview.rendered}</p>
              <p className="mt-2 text-xs text-muted">FY {preview.fiscal_year} · {preview.implementation} · {preview.period_open ? 'period open' : 'period closed'}</p>
            </div>
          )}
          {!selected && <p className="mt-4 text-sm text-muted">Choose Preview on a series to see its next number without allocating it.</p>}
        </aside>
      </div>

      <SequenceStatusDrawer sequenceKey={statusKey} open={Boolean(statusKey)} onClose={() => setStatusKey(null)} onViewBlocks={(key) => { setStatusKey(null); navigate(`/settings/numbering/blocks?key=${encodeURIComponent(key)}`) }} />

      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={`Edit series ${editing?.key ?? ''}`}
        description="Pattern changes are validated against the document channel before saving."
        size="lg"
        footer={<><button type="button" className="btn-secondary" onClick={() => setEditing(null)}>Cancel</button><button type="button" className="btn-primary" data-testid="sequence-save" disabled={saving} onClick={saveEditor}>{saving ? 'Saving…' : 'Save series'}</button></>}
      >
        {editing?.locked && <div className="mb-4"><LockedNote row={editing} /></div>}
        <PatternBuilder sequence={editing} onChange={setForm} locked={Boolean(editing?.locked)} />
      </Modal>

      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="Create a new series"
        description="New series start with a validated pattern and their own financial-year counter."
        size="lg"
        footer={<><button type="button" className="btn-secondary" onClick={() => setCreating(false)}>Cancel</button><button type="button" className="btn-primary" data-testid="series-create-submit" disabled={saving} onClick={createSeries}>{saving ? 'Creating…' : 'Create series'}</button></>}
      >
        <PatternBuilder sequence={null} onChange={setForm} locked={false} />
      </Modal>
    </div>
  )
}

function LockedNote({ row }) {
  return (
    <p className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-700" data-testid={`sequence-locked-${row.key}`}>
      <strong>Locked after first allocation (SE-14).</strong> {row.preview || row.pattern || 'An issued number'} was already handed out, so implementation, pattern, reset policy and padding are read-only. Create a new series to change the format.
    </p>
  )
}

function SequenceActions({ row, onPreview, onStatus, onEdit, onBlocks, onGaps }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`sequence-preview-${row.key}`} onClick={() => onPreview(row)}><Eye size={13} /> Preview</button>
      <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`sequence-status-${row.key}`} onClick={() => onStatus(row.key)}>Status</button>
      <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`sequence-edit-${row.key}`} onClick={() => onEdit(row)} disabled={row.locked}><Pencil size={13} /> Edit</button>
      <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`sequence-blocks-${row.key}`} onClick={() => onBlocks(row.key)}><Blocks size={13} /> Blocks</button>
      <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" data-testid={`sequence-gaps-${row.key}`} onClick={() => onGaps(row.key)}><BadgeIndianRupee size={13} /> Gaps</button>
    </div>
  )
}
