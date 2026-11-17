import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { fetchLookup } from '../lib/lookups'
import { cn } from '../lib/format'
import { Spinner } from './ui'

export function RemoteSelect({ lookup, value, onChange, placeholder = 'Select…', disabled, allowEmpty = true }) {
  const [options, setOptions] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    setLoading(true)
    fetchLookup(lookup)
      .then((items) => active && setOptions(items))
      .catch(() => active && setOptions([]))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [lookup])

  return (
    <div className="relative">
      <select
        className="input appearance-none pr-9"
        value={value ?? ''}
        onChange={(event) => onChange(event.target.value || null)}
        disabled={disabled || loading}
      >
        {allowEmpty && <option value="">{loading ? 'Loading…' : placeholder}</option>}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
        {value && !options.some((option) => option.value === value) && (
          <option value={value}>{String(value).slice(0, 8)}…</option>
        )}
      </select>
      {loading && <Spinner className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />}
    </div>
  )
}

export function MultiSelect({ lookup, value = [], onChange, disabled }) {
  const [options, setOptions] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    fetchLookup(lookup)
      .then((items) => active && setOptions(items))
      .catch(() => active && setOptions([]))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [lookup])

  const selected = Array.isArray(value) ? value : []

  return (
    <div>
      <select
        multiple
        size={6}
        disabled={disabled || loading}
        className="input min-h-[132px] py-2 text-xs"
        value={selected}
        onChange={(event) =>
          onChange(Array.from(event.target.selectedOptions).map((option) => option.value))
        }
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <div className="mt-1.5 flex items-center justify-between text-[11px] text-muted">
        <span>{selected.length} selected{loading ? ' · loading options…' : ''}</span>
        {selected.length > 0 && (
          <button type="button" className="font-semibold text-accent hover:underline" onClick={() => onChange([])}>
            Clear
          </button>
        )}
      </div>
    </div>
  )
}

export function Field({ field, value, onChange, error }) {
  const id = `field-${field.name}`
  const common = { id, name: field.name, required: field.required }

  let control
  switch (field.type) {
    case 'select':
      control = (
        <select className="input" value={value ?? ''} onChange={(event) => onChange(event.target.value || null)} {...common}>
          {(!field.required || field.allowEmpty) && <option value="">{field.placeholder || 'Select…'}</option>}
          {(field.options ?? []).map((option) => {
            const normalized = typeof option === 'string' ? { value: option, label: option } : option
            return (
              <option key={normalized.value} value={normalized.value}>
                {normalized.label}
              </option>
            )
          })}
        </select>
      )
      break
    case 'reference':
      control = (
        <RemoteSelect
          lookup={field.lookup}
          value={value}
          onChange={onChange}
          placeholder={field.placeholder}
          disabled={field.disabled}
        />
      )
      break
    case 'multiselect':
      control = (
        <MultiSelect lookup={field.lookup} value={value} onChange={onChange} disabled={field.disabled} />
      )
      break
    case 'textarea':
      control = (
        <textarea
          className="input min-h-[90px] resize-y"
          value={value ?? ''}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.placeholder}
          {...common}
        />
      )
      break
    case 'checkbox':
      return (
        <label
          htmlFor={id}
          className="flex cursor-pointer items-start gap-3 rounded-xl border border-line bg-surface p-3.5 transition hover:bg-surface-2"
        >
          <input
            id={id}
            type="checkbox"
            className="mt-0.5 h-4 w-4 rounded border-line text-primary accent-[var(--color-primary)]"
            checked={Boolean(value)}
            onChange={(event) => onChange(event.target.checked)}
          />
          <span>
            <span className="block text-sm font-semibold text-ink">{field.label}</span>
            {field.help && <span className="mt-0.5 block text-xs text-muted">{field.help}</span>}
          </span>
        </label>
      )
    case 'json':
      control = (
        <textarea
          className="input min-h-[110px] resize-y font-mono text-xs"
          value={typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2)}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.placeholder || '{}'}
          {...common}
        />
      )
      break
    case 'number':
      control = (
        <input
          type="number"
          className="input"
          value={value ?? ''}
          step={field.step ?? 'any'}
          min={field.min}
          onChange={(event) => onChange(event.target.value === '' ? '' : event.target.value)}
          placeholder={field.placeholder}
          {...common}
        />
      )
      break
    case 'date':
      control = (
        <input
          type="date"
          className="input"
          value={value ?? ''}
          onChange={(event) => onChange(event.target.value || null)}
          {...common}
        />
      )
      break
    case 'datetime':
      control = (
        <input
          type="datetime-local"
          className="input"
          value={value ?? ''}
          onChange={(event) => onChange(event.target.value || null)}
          {...common}
        />
      )
      break
    case 'time':
      control = (
        <input
          type="time"
          className="input"
          value={value ?? ''}
          onChange={(event) => onChange(event.target.value || null)}
          {...common}
        />
      )
      break
    default:
      control = (
        <input
          type={field.type ?? 'text'}
          className="input"
          value={value ?? ''}
          onChange={(event) => onChange(event.target.value)}
          placeholder={field.placeholder}
          {...common}
        />
      )
  }

  return (
    <div className={cn(field.colSpan === 2 ? 'sm:col-span-2' : field.colSpan === 3 ? 'sm:col-span-3' : '')}>
      {field.label && field.type !== 'checkbox' && (
        <label htmlFor={id} className="label">
          {field.label}
          {field.required && <span className="ml-1 text-accent">*</span>}
        </label>
      )}
      {control}
      {field.help && field.type !== 'checkbox' && <p className="mt-1 text-[11px] text-muted">{field.help}</p>}
      {error && <p className="mt-1 text-[11px] font-semibold text-rose-600">{error}</p>}
    </div>
  )
}

export function FormGrid({ fields, values, onChange, errors = {}, columns = 2 }) {
  return (
    <div className={cn('grid gap-4', columns === 3 ? 'sm:grid-cols-3' : 'sm:grid-cols-2')}>
      {fields.map((field) => (
        <Field
          key={field.name}
          field={field}
          value={values[field.name]}
          onChange={(value) => onChange(field.name, value)}
          error={errors[field.name]}
        />
      ))}
    </div>
  )
}

export function LineItemsInput({ field, value = [], onChange }) {
  const rows = Array.isArray(value) ? value : []
  const [seed, setSeed] = useState(0)
  const makeEmpty = () => {
    const row = { __key: `${Date.now()}-${seed}-${rows.length}` }
    for (const column of field.columns) row[column.name] = column.default ?? ''
    setSeed((current) => current + 1)
    return row
  }

  const update = (index, name, nextValue) => {
    onChange(rows.map((row, rowIndex) => (rowIndex === index ? { ...row, [name]: nextValue } : row)))
  }

  const remove = (index) => onChange(rows.filter((_, rowIndex) => rowIndex !== index))
  const add = () => onChange([...rows, makeEmpty()])

  return (
    <div className="sm:col-span-2">
      <div className="mb-2 flex items-center justify-between">
        <span className="label mb-0">
          {field.label}
          {field.required && <span className="ml-1 text-accent">*</span>}
        </span>
        <button type="button" className="btn-secondary px-2.5 py-1.5 text-xs" onClick={add}>
          <Plus size={14} /> Add line
        </button>
      </div>
      <div className="overflow-hidden rounded-xl border border-line">
        <div className="hidden items-center gap-2 bg-surface-2 px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] text-muted sm:flex">
          {field.columns.map((column) => (
            <span key={column.name} style={{ flex: column.flex ?? 1 }} className={column.width}>
              {column.label}
            </span>
          ))}
          <span className="w-8" />
        </div>
        {rows.length === 0 && (
          <div className="px-4 py-6 text-center text-xs text-muted">
            No lines yet. Add at least one line item.
          </div>
        )}
        {rows.map((row, index) => (
          <div key={row.__key ?? index} className="flex flex-col gap-2 border-t border-line bg-surface p-3 sm:flex-row sm:items-center">
            {field.columns.map((column) => (
              <div key={column.name} style={{ flex: column.flex ?? 1 }} className={cn('min-w-0', column.width)}>
                <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-muted sm:hidden">
                  {column.label}
                </span>
                {column.type === 'reference' ? (
                  <RemoteSelect
                    lookup={column.lookup}
                    value={row[column.name]}
                    onChange={(next) => update(index, column.name, next)}
                    placeholder={column.placeholder ?? 'Select…'}
                  />
                ) : column.type === 'select' ? (
                  <select
                    className="input py-2 text-xs"
                    value={row[column.name] ?? ''}
                    onChange={(event) => update(index, column.name, event.target.value)}
                  >
                    <option value="">Select…</option>
                    {(column.options ?? []).map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type={column.type === 'number' ? 'number' : 'text'}
                    step={column.step ?? 'any'}
                    className="input py-2 text-xs"
                    value={row[column.name] ?? ''}
                    placeholder={column.placeholder}
                    onChange={(event) => update(index, column.name, event.target.value)}
                  />
                )}
              </div>
            ))}
            <button
              type="button"
              className="mt-1 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted transition hover:bg-rose-50 hover:text-rose-600 sm:mt-0"
              onClick={() => remove(index)}
              aria-label="Remove line"
            >
              <Trash2 size={15} />
            </button>
          </div>
        ))}
      </div>
      {field.help && <p className="mt-1.5 text-[11px] text-muted">{field.help}</p>}
    </div>
  )
}
