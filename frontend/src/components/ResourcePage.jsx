import { useCallback, useEffect, useMemo, useState } from 'react'
import { Download, Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { api, apiErrorMessage } from '../lib/api'
import { cn, debounce, today } from '../lib/format'
import { useAuth } from '../store/auth'
import { toast } from '../store/toast'
import { DataTable } from './DataTable'
import { FormGrid, LineItemsInput } from './Form'
import { EmptyState, Modal, PageHeader, Pagination, SearchInput, Spinner } from './ui'

function emptyLine(field) {
  const row = { __key: `${Date.now()}-${Math.random()}` }
  for (const column of field.columns) row[column.name] = column.default ?? ''
  return row
}

function initialValues(fields) {
  const values = {}
  for (const field of fields) {
    if (field.type === 'line_items') {
      const count = field.initialRows ?? 1
      values[field.name] = Array.from({ length: count }, () => emptyLine(field))
      continue
    }
    if (field.type === 'checkbox') {
      values[field.name] = field.default ?? false
      continue
    }
    values[field.name] = field.default === 'today' ? today() : field.default ?? ''
  }
  return values
}

function editValues(record, fields) {
  const values = {}
  for (const field of fields) {
    const value = record[field.name]
    if (field.type === 'line_items') {
      values[field.name] = Array.isArray(value)
        ? value.map((row, index) => ({ ...row, __key: `${Date.now()}-${index}` }))
        : []
    } else if (field.type === 'json') {
      values[field.name] = JSON.stringify(value ?? {}, null, 2)
    } else if (field.type === 'datetime') {
      values[field.name] = value ? String(value).slice(0, 16) : ''
    } else if (field.type === 'date') {
      values[field.name] = value ? String(value).slice(0, 10) : ''
    } else if (field.type === 'time') {
      values[field.name] = value ? String(value).slice(0, 5) : ''
    } else {
      values[field.name] = value ?? (field.type === 'checkbox' ? false : '')
    }
  }
  return values
}

function buildPayload(fields, values) {
  const payload = {}
  for (const field of fields) {
    const value = values[field.name]
    if (field.type === 'line_items') {
      payload[field.name] = (value ?? []).map((row) => {
        const line = {}
        for (const column of field.columns) {
          const raw = row[column.name]
          if (raw === '' || raw === null || raw === undefined) continue
          line[column.name] = raw
        }
        return line
      })
      continue
    }
    if (value === '' || value === undefined) {
      if (field.includeEmpty) payload[field.name] = null
      continue
    }
    if (field.type === 'json') {
      try {
        payload[field.name] = value ? JSON.parse(value) : {}
      } catch {
        payload[field.name] = value
      }
      continue
    }
    if (field.type === 'datetime') {
      payload[field.name] = new Date(value).toISOString()
      continue
    }
    if (field.type === 'checkbox') {
      payload[field.name] = Boolean(value)
      continue
    }
    payload[field.name] = value
  }
  return payload
}

function validate(fields, values) {
  const errors = {}
  for (const field of fields) {
    if (!field.required) continue
    const value = values[field.name]
    if (field.type === 'line_items') {
      if (!Array.isArray(value) || value.length === 0) {
        errors[field.name] = 'Add at least one line.'
      } else {
        const missing = value.some((row) =>
          field.columns.some((column) => column.required && !row[column.name]),
        )
        if (missing) errors[field.name] = 'Complete all required line fields.'
      }
    } else if (value === '' || value === null || value === undefined) {
      errors[field.name] = 'This field is required.'
    }
  }
  return errors
}

function toCsv(columns, rows) {
  const header = columns.map((column) => column.label)
  const lines = rows.map((row) =>
    columns.map((column) => {
      const value = column.csv ? column.csv(row) : row[column.key]
      return `"${String(value ?? '').replaceAll('"', '""')}"`
    }),
  )
  return [header, ...lines].map((line) => line.join(',')).join('\n')
}

export default function ResourcePage({
  title,
  eyebrow,
  description,
  endpoint,
  permission,
  columns,
  fields,
  editFields,
  searchPlaceholder = 'Search…',
  filters = [],
  defaultFilters = {},
  createLabel = 'New record',
  canCreate = true,
  canEdit = true,
  canDelete = true,
  rowActions,
  readPermission,
  createPermission,
  updatePermission,
  deletePermission,
  emptyTitle = 'Nothing here yet',
  emptyDescription = 'Create the first record to get started.',
  emptyIcon,
  size = 20,
  onLoaded,
  rowKey,
  headerActions,
}) {
  const can = useAuth((state) => state.can)
  const allowedRead = can(readPermission ?? `${permission}.read`)
  const allowedCreate = canCreate && can(createPermission ?? `${permission}.create`)
  const allowedUpdate = canEdit && can(updatePermission ?? `${permission}.update`)
  const allowedDelete = canDelete && can(deletePermission ?? `${permission}.delete`)

  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [searchText, setSearchText] = useState('')
  const [activeFilters, setActiveFilters] = useState(defaultFilters)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)

  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [values, setValues] = useState({})
  const [formErrors, setFormErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleting, setDeleting] = useState(false)

  const formFields = editing ? editFields ?? fields : fields

  const load = useCallback(
    async (options = {}) => {
      if (!allowedRead) {
        setLoading(false)
        return
      }
      const targetPage = options.page ?? page
      if (options.refresh) setRefreshing(true)
      else setLoading(true)
      setError(null)
      try {
        const { data } = await api.get(endpoint, {
          params: {
            page: targetPage,
            size,
            ...(search ? { q: search } : {}),
            ...Object.fromEntries(Object.entries(activeFilters).filter(([, value]) => value !== '' && value != null)),
          },
        })
        if (Array.isArray(data)) {
          setRows(data)
          setTotal(data.length)
          setPages(1)
        } else {
          setRows(data.items ?? [])
          setTotal(data.total ?? 0)
          setPages(data.pages ?? 1)
        }
        onLoaded?.(data)
      } catch (requestError) {
        setError(apiErrorMessage(requestError, 'Unable to load records.'))
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [activeFilters, allowedRead, endpoint, onLoaded, page, search, size],
  )

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    setPage(1)
  }, [search, activeFilters])

  const runSearch = useMemo(() => debounce((value) => setSearch(value), 300), [])

  const openCreate = () => {
    setEditing(null)
    setValues(initialValues(fields))
    setFormErrors({})
    setOpen(true)
  }

  const openEdit = (record) => {
    setEditing(record)
    setValues(editValues(record, editFields ?? fields))
    setFormErrors({})
    setOpen(true)
  }

  const updateValue = (name, value) => setValues((current) => ({ ...current, [name]: value }))

  const submit = async (event) => {
    event.preventDefault()
    const nextErrors = validate(formFields, values)
    setFormErrors(nextErrors)
    if (Object.keys(nextErrors).length) return

    setSaving(true)
    try {
      const payload = buildPayload(formFields, values)
      if (editing) {
        await api.patch(`${endpoint}/${editing.id}`, payload)
        toast.success('Changes saved', `${title} record updated.`)
      } else {
        await api.post(endpoint, payload)
        toast.success('Record created', `${title} record added successfully.`)
      }
      setOpen(false)
      await load({ refresh: true })
    } catch (requestError) {
      toast.error('Could not save', apiErrorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.delete(`${endpoint}/${deleteTarget.id}`)
      toast.success('Record archived', `${title} record was removed.`)
      setDeleteTarget(null)
      await load({ refresh: true })
    } catch (requestError) {
      toast.error('Could not delete', apiErrorMessage(requestError))
    } finally {
      setDeleting(false)
    }
  }

  const exportCsv = () => {
    const csv = toCsv(columns, rows)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${String(title).toLowerCase().replace(/\s+/g, '-')}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  if (!allowedRead) {
    return (
      <EmptyState
        title="You don’t have access to this area"
        description="Ask an administrator to grant the matching read permission for your role."
      />
    )
  }

  return (
    <>
      <PageHeader
        eyebrow={eyebrow}
        title={title}
        description={description}
        actions={
          <>
            {headerActions}
            <button type="button" className="btn-secondary" onClick={exportCsv} disabled={!rows.length}>
              <Download size={15} /> Export
            </button>
            <button type="button" className="btn-secondary" onClick={() => load({ refresh: true })}>
              <RefreshCw size={15} className={cn(refreshing && 'animate-spin')} />
            </button>
            {allowedCreate && (
              <button type="button" className="btn-primary" onClick={openCreate}>
                <Plus size={16} /> {createLabel}
              </button>
            )}
          </>
        }
      />

      <div className="card overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-line px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-1 flex-wrap items-center gap-2">
            <SearchInput
              className="w-full sm:w-72"
              placeholder={searchPlaceholder}
              value={searchText}
              onChange={(value) => {
                setSearchText(value)
                runSearch(value)
              }}
            />
            {filters.map((filter) => (
              <select
                key={filter.name}
                className="input w-auto min-w-[130px] py-2.5 text-xs"
                value={activeFilters[filter.name] ?? ''}
                onChange={(event) =>
                  setActiveFilters((current) => ({ ...current, [filter.name]: event.target.value }))
                }
              >
                <option value="">{filter.label}</option>
                {(typeof filter.options === 'function' ? filter.options(rows) : filter.options).map((option) => {
                  const normalized = typeof option === 'string' ? { value: option, label: option } : option
                  return (
                    <option key={normalized.value} value={normalized.value}>
                      {normalized.label}
                    </option>
                  )
                })}
              </select>
            ))}
          </div>
          <div className="flex items-center gap-3 text-xs text-muted">
            <span className="rounded-full bg-surface-2 px-3 py-1 font-bold text-ink-soft">
              {total} record{total === 1 ? '' : 's'}
            </span>
            {search && (
              <button
                type="button"
                className="font-semibold text-accent hover:underline"
                onClick={() => {
                  setSearchText('')
                  setSearch('')
                }}
              >
                Clear search
              </button>
            )}
          </div>
        </div>

        {error ? (
          <EmptyState
            title="Could not load this list"
            description={error}
            action={
              <button type="button" className="btn-secondary" onClick={() => load({ refresh: true })}>
                Try again
              </button>
            }
          />
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            loading={loading}
            rowKey={rowKey}
            empty={
              <EmptyState
                icon={emptyIcon}
                title={emptyTitle}
                description={emptyDescription}
                action={
                  allowedCreate ? (
                    <button type="button" className="btn-primary" onClick={openCreate}>
                      <Plus size={16} /> {createLabel}
                    </button>
                  ) : null
                }
              />
            }
            rowActions={(row) => (
              <>
                {rowActions?.map((action) => {
                  if (action.show && !action.show(row)) return null
                  const Icon = action.icon
                  return (
                    <button
                      key={action.label}
                      type="button"
                      title={action.label}
                      disabled={action.disabled?.(row)}
                      className={cn(
                        'inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink disabled:opacity-30',
                        action.tone === 'danger' && 'hover:bg-rose-50 hover:text-rose-600',
                        action.tone === 'positive' && 'hover:bg-emerald-50 hover:text-emerald-700',
                      )}
                      onClick={() => action.onClick(row, { reload: () => load({ refresh: true }) })}
                    >
                      {Icon ? <Icon size={15} /> : <span className="px-2 text-[10px] font-bold">{action.label}</span>}
                    </button>
                  )
                })}
                {allowedUpdate && (
                  <button
                    type="button"
                    title="Edit"
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-ink"
                    onClick={() => openEdit(row)}
                  >
                    <Pencil size={15} />
                  </button>
                )}
                {allowedDelete && (
                  <button
                    type="button"
                    title="Archive"
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-rose-50 hover:text-rose-600"
                    onClick={() => setDeleteTarget(row)}
                  >
                    <Trash2 size={15} />
                  </button>
                )}
              </>
            )}
          />
        )}

        {!error && <Pagination page={page} pages={pages} total={total} size={size} onPage={setPage} />}
      </div>

      <Modal
        open={open}
        onClose={() => !saving && setOpen(false)}
        title={editing ? `Edit ${title.toLowerCase()} record` : createLabel}
        description={
          editing ? 'Update the fields below and save your changes.' : 'Fill in the details to add a new record.'
        }
        size={formFields.some((field) => field.type === 'line_items') ? 'lg' : 'md'}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setOpen(false)} disabled={saving}>
              Cancel
            </button>
            <button type="button" className="btn-primary" onClick={submit} disabled={saving}>
              {saving && <Spinner className="h-4 w-4" />}
              {editing ? 'Save changes' : 'Create record'}
            </button>
          </>
        }
      >
        <form onSubmit={submit}>
          <FormGrid fields={formFields.filter((field) => field.type !== 'line_items')} values={values} onChange={updateValue} errors={formErrors} />
          {formFields
            .filter((field) => field.type === 'line_items')
            .map((field) => (
              <div key={field.name} className="mt-4 grid gap-4 sm:grid-cols-2">
                <LineItemsInput field={field} value={values[field.name]} onChange={(next) => updateValue(field.name, next)} />
                {formErrors[field.name] && (
                  <p className="sm:col-span-2 text-xs font-semibold text-rose-600">{formErrors[field.name]}</p>
                )}
              </div>
            ))}
        </form>
      </Modal>

      <Modal
        open={Boolean(deleteTarget)}
        onClose={() => !deleting && setDeleteTarget(null)}
        title="Archive this record?"
        description="The record will be soft-deleted and hidden from lists. This is reversible by an administrator."
        size="sm"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setDeleteTarget(null)} disabled={deleting}>
              Keep record
            </button>
            <button type="button" className="btn-danger" onClick={confirmDelete} disabled={deleting}>
              {deleting && <Spinner className="h-4 w-4" />}
              Archive record
            </button>
          </>
        }
      >
        <p className="text-sm text-ink-soft">
          {deleteTarget ? (
            <>
              You’re about to archive <span className="font-bold text-ink">{deleteTarget.name ?? deleteTarget.title ?? deleteTarget.invoice_number ?? deleteTarget.id}</span>.
            </>
          ) : null}
        </p>
      </Modal>
    </>
  )
}
