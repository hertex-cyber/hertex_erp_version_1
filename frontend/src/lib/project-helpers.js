export const AI_ACTION_TYPES = [
  'draft_project',
  'draft_checklist',
  'draft_status_update',
  'draft_reassignment',
  'draft_risk',
  'draft_mitigation_task',
  'draft_billing_run',
  'draft_stakeholder_update',
  'draft_triage',
  'draft_import_mapping',
  'draft_work_item',
]

export const PROHIBITED_AI_ACTIONS = [
  'auto_close_work_item',
  'close_work_item',
  'approve_timesheet',
  'approve_time',
  'post_invoice',
  'post_billing',
  'change_baseline',
  'book_capacity',
  'send_notification',
  'deny_leave',
  'change_access',
  'terminate_employee',
]

export const PROJECT_ASSISTANT_PROMPTS = [
  'Which projects are at risk this month?',
  'Show unbilled approved time.',
  'What is the critical path?',
  'Who is over-allocated next week?',
  'Summarize the latest status report.',
  'What changed in the baseline?',
  'Which work items are blocked by customer inputs?',
  'Show cycle time by team for the last three sprints.',
  'What can we invoice this week?',
]

export function topFeatures(features) {
  const entries = Array.isArray(features)
    ? features.map((feature) => [feature?.name ?? feature?.feature ?? feature?.label ?? 'feature', Number(feature?.value ?? feature?.score ?? 0)])
    : Object.entries(features ?? {}).map(([name, value]) => [name, Number(typeof value === 'object' ? value?.value ?? value?.score ?? 0 : value)])
  return entries
    .filter(([, value]) => Number.isFinite(value))
    .sort((first, second) => second[1] - first[1])
    .slice(0, 3)
}

export function isProhibitedAiAction(row) {
  const proposed = row?.proposed_json ?? {}
  const candidates = [row?.action_type, proposed.action, proposed.action_type, proposed.code, ...(Array.isArray(proposed.actions) ? proposed.actions : [])]
  return candidates.some((candidate) =>
    PROHIBITED_AI_ACTIONS.includes(String(typeof candidate === 'object' ? candidate?.type ?? candidate?.code ?? '' : candidate).toLowerCase()),
  )
}

export function aiActionScope(row) {
  const proposed = row?.proposed_json ?? {}
  const scope = proposed.scope ?? proposed.proposed_scope ?? row?.scope
  if (!scope) return '—'
  return typeof scope === 'string' ? scope : JSON.stringify(scope)
}

export function earnedValue(row) {
  const budget = Number(row?.budget ?? 0)
  const cost = Number(row?.cost ?? 0)
  const earned = Number(row?.earned_value ?? 0)
  const cpi = Number(row?.cpi ?? 0)
  const eac = cpi > 0 ? budget / cpi : cost + Math.max(0, budget - earned)
  return { eac, etc: Math.max(0, eac - cost) }
}

export const ROW_DATE_KEYS = [
  'generated_at',
  'week_start',
  'end_date',
  'due_date',
  'accepted_at',
  'submitted_at',
  'executed_at',
  'posted_at',
  'start_date',
  'entry_date',
]

export function filterReportRows(rows, filters = {}) {
  return (rows ?? []).filter((row) => {
    if (filters.projectId && row.project_id && row.project_id !== filters.projectId) return false
    if (filters.team && row.employee_id && row.employee_id !== filters.team) return false
    if (!filters.dateFrom && !filters.dateTo) return true
    const dateKey = ROW_DATE_KEYS.find((key) => row[key])
    if (!dateKey) return true
    const value = String(row[dateKey]).slice(0, 10)
    if (filters.dateFrom && value < filters.dateFrom) return false
    if (filters.dateTo && value > filters.dateTo) return false
    return true
  })
}

export function scopedProjectQuestion(text, project) {
  const question = String(text ?? '').trim()
  const name = project?.name ?? project?.code
  if (!question || !name) return question
  if (question.toLowerCase().includes(String(name).toLowerCase())) return question
  return `${question.replace(/[?？]\s*$/, '')} for project ${name}`
}
