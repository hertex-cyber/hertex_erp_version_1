import { api } from './api'
import { dateLabel } from './format'

const text = (value, fallback = '') => value ?? fallback

export const LOOKUPS = {
  products: {
    endpoint: '/inventory/products',
    label: (item) => `${text(item.sku)} · ${text(item.name)}`,
  },
  categories: { endpoint: '/inventory/categories', label: (item) => item.name },
  warehouses: { endpoint: '/warehouse/warehouses', label: (item) => `${item.code} · ${item.name}` },
  bins: { endpoint: '/warehouse/bins', label: (item) => `${item.code}${item.name ? ` · ${item.name}` : ''}` },
  customers: { endpoint: '/sales/customers', label: (item) => `${item.code} · ${item.name}` },
  vendors: { endpoint: '/procurement/vendors', label: (item) => `${item.code} · ${item.name}` },
  accounts: { endpoint: '/finance/accounts', label: (item) => `${item.code} · ${item.name}` },
  'account-groups': { endpoint: '/finance/account-groups', label: (item) => `${item.code} · ${item.name}` },
  invoices: { endpoint: '/finance/invoices', label: (item) => item.invoice_number },
  users: { endpoint: '/users', label: (item) => `${item.full_name} · ${item.email}` },
  roles: { endpoint: '/roles', label: (item) => item.name },
  companies: { endpoint: '/crm/companies', label: (item) => item.name },
  contacts: { endpoint: '/crm/contacts', label: (item) => `${item.first_name} ${item.last_name ?? ''}`.trim() },
  leads: { endpoint: '/crm/leads', label: (item) => item.name },
  employees: { endpoint: '/hr/employees', label: (item) => `${item.employee_code} · ${item.first_name} ${item.last_name ?? ''}`.trim() },
  departments: { endpoint: '/hr/departments', label: (item) => item.name },
  projects: { endpoint: '/projects', label: (item) => `${text(item.code)} · ${text(item.name)}`.replace(/^ · | · $/g, '') },
  portfolios: { endpoint: '/projects/portfolios', label: (item) => `${item.code} · ${item.name}` },
  programs: { endpoint: '/projects/programs', label: (item) => `${item.code} · ${item.name}` },
  phases: { endpoint: '/projects/phases', label: (item) => item.name },
  sprints: { endpoint: '/projects/sprints', label: (item) => `${item.number ?? ''} · ${item.name}`.trim() },
  boards: { endpoint: '/projects/boards', label: (item) => item.name },
  boardColumns: { endpoint: '/projects/board-columns', label: (item) => item.name },
  workItems: { endpoint: '/projects/work-items', label: (item) => `${item.number ?? ''} · ${item.title}`.trim() },
  milestones: { endpoint: '/projects/milestones', label: (item) => item.name },
  timeEntries: { endpoint: '/projects/time-entries', label: (item) => `${dateLabel(item.entry_date)} · ${item.hours}h` },
  timesheets: { endpoint: '/projects/timesheets', label: (item) => `${dateLabel(item.week_start)} · ${item.employee_id ?? ''}` },
  billingRuns: { endpoint: '/projects/billing-runs', label: (item) => `${item.period} · ${item.status}` },
  budgets: { endpoint: '/projects/budgets', label: (item) => `v${item.version} · ${item.status}` },
  resourceRoles: { endpoint: '/projects/resource-roles', label: (item) => `${item.code} · ${item.name}` },
  risks: { endpoint: '/projects/risks', label: (item) => item.title },
  issues: { endpoint: '/projects/issues', label: (item) => item.title },
  decisions: { endpoint: '/projects/decisions', label: (item) => item.title },
  goals: { endpoint: '/projects/goals', label: (item) => item.title },
  automationRules: { endpoint: '/projects/automation-rules', label: (item) => item.name },
  aiSignals: { endpoint: '/projects/ai-signals', label: (item) => `${item.signal_type} · ${item.entity_id}` },
  workItemLinks: { endpoint: '/projects/work-item-links', label: (item) => `${item.link_type} · ${item.from_work_item_id} → ${item.to_work_item_id}` },
  labels: { endpoint: '/projects/labels', label: (item) => item.name },
  customFields: { endpoint: '/projects/custom-fields', label: (item) => item.name },
  fieldValues: { endpoint: '/projects/field-values', label: (item) => `${item.field_id} · ${item.entity_id}` },
  workflows: { endpoint: '/projects/workflows', label: (item) => item.name },
  transitions: { endpoint: '/projects/transitions', label: (item) => `${item.from_status} → ${item.to_status}` },
  approvals: { endpoint: '/projects/approvals', label: (item) => `${text(item.approval_type)} · ${text(item.status)}` },
  templates: { endpoint: '/projects/templates', label: (item) => item.name },
  baselines: { endpoint: '/projects/baselines', label: (item) => `${text(item.name)} · v${text(item.version, '1')}` },
  baselineSnapshots: { endpoint: '/projects/baseline-snapshots', label: (item) => `${text(item.entity_type)} · ${dateLabel(item.captured_at)}` },
  releases: { endpoint: '/projects/releases', label: (item) => `${text(item.version)} · ${text(item.name)}` },
  changeRequests: { endpoint: '/projects/change-requests', label: (item) => item.title },
  timesheetEntries: { endpoint: '/projects/timesheet-entries', label: (item) => `${dateLabel(item.work_date)} · ${item.hours}h` },
  costEntries: { endpoint: '/projects/cost-entries', label: (item) => `${text(item.category)} · ${dateLabel(item.entry_date)}` },
  billingLines: { endpoint: '/projects/billing-lines', label: (item) => `${text(item.description)} · ${text(item.amount)}` },
  invoiceLinks: { endpoint: '/projects/invoice-links', label: (item) => `${text(item.invoice_id)} · ${text(item.billing_run_id)}` },
  budgetRevisions: { endpoint: '/projects/budget-revisions', label: (item) => `v${text(item.version)} · ${text(item.status)}` },
  employeeSkills: { endpoint: '/projects/employee-skills', label: (item) => `${text(item.skill)} · ${text(item.proficiency)}` },
  capacityCalendars: { endpoint: '/projects/capacity-calendars', label: (item) => `${text(item.name)} · ${text(item.timezone)}` },
  workloadSnapshots: { endpoint: '/projects/workload-snapshots', label: (item) => `${dateLabel(item.snapshot_date)} · ${text(item.employee_id)}` },
  retrospectives: { endpoint: '/projects/retrospectives', label: (item) => `${text(item.sprint_id)} · ${dateLabel(item.retro_date)}` },
  comments: { endpoint: '/projects/comments', label: (item) => `${text(item.entity_type)} · ${String(item.body ?? '').slice(0, 32)}` },
  attachments: { endpoint: '/projects/attachments', label: (item) => text(item.title) || text(item.document_id) },
  activities: { endpoint: '/projects/activities', label: (item) => `${text(item.action)} · ${dateLabel(item.created_at)}` },
  integrations: { endpoint: '/projects/integrations', label: (item) => `${text(item.provider)} · ${text(item.external_id)}` },
  imports: { endpoint: '/projects/imports', label: (item) => `${text(item.provider)} · ${text(item.status)}` },
  importBatches: { endpoint: '/projects/import-batches', label: (item) => `${text(item.provider)} · ${text(item.status)} · ${text(item.total_rows)} rows` },
  aiActions: { endpoint: '/projects/ai-actions', label: (item) => `${text(item.action_type)} · ${text(item.status)}` },
  automationRuns: { endpoint: '/projects/automation-runs', label: (item) => `${text(item.rule_id)} · ${text(item.status)}` },
  outbox: { endpoint: '/projects/outbox', label: (item) => `${text(item.event_type)} · ${text(item.status)}` },
  salesOrders: { endpoint: '/sales/orders', label: (item) => `${item.order_number} · ${item.status}` },
  requisitions: { endpoint: '/procurement/requisitions', label: (item) => item.requisition_number },
  purchaseOrders: { endpoint: '/procurement/purchase-orders', label: (item) => item.po_number },
  permissions: { endpoint: '/roles/permissions/catalog', label: (item) => item.code },
  bankAccounts: { endpoint: '/finance/bank-accounts', label: (item) => `${item.bank_name} · ${item.account_number}` },
  taxCodes: { endpoint: '/finance/tax/codes', label: (item) => `${item.code} · ${item.description}` },
  taxRegistrations: { endpoint: '/finance/tax/registrations', label: (item) => `${item.gstin} · ${item.state_code}` },
  legalEntities: { endpoint: '/finance/legal-entities', label: (item) => `${item.code} · ${item.name}` },
  financeBranches: { endpoint: '/finance/branches', label: (item) => `${item.code} · ${item.name}` },
  costCenters: { endpoint: '/finance/cost-centers', label: (item) => `${item.code} · ${item.name}` },
  financeDepartments: { endpoint: '/finance/departments', label: (item) => `${item.code} · ${item.name}` },
  financeBudgets: { endpoint: '/finance/budgets', label: (item) => item.name },
  segments: { endpoint: '/marketing/segments', label: (item) => item.name },
  campaigns: { endpoint: '/marketing/campaigns', label: (item) => item.name },
  sessions: { endpoint: '/pos/sessions', label: (item) => `${item.terminal_name} · ${item.status}` },
  customersRaw: { endpoint: '/sales/customers', label: (item) => item.name },
}

export async function fetchLookup(key, search = '') {
  const config = LOOKUPS[key]
  if (!config) return []
  const params = { size: 200 }
  if (search) params.q = search
  const { data } = await api.get(config.endpoint, { params })
  const items = Array.isArray(data) ? data : data.items ?? []
  return items.map((item) => ({ value: item.id, label: config.label(item), raw: item }))
}

export function lookupLabel(key, id, cache = {}) {
  if (!id) return '—'
  const options = cache[key] ?? []
  return options.find((option) => option.value === id)?.label ?? id
}
