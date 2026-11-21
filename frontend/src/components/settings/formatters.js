export function formatSettingValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

export function formatActor(row) {
  return row?.actor || row?.actor_email || row?.rotated_by || row?.actor_id || 'system'
}
