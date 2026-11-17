import { api } from './api'

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
  invoices: { endpoint: '/finance/invoices', label: (item) => item.invoice_number },
  users: { endpoint: '/users', label: (item) => `${item.full_name} · ${item.email}` },
  roles: { endpoint: '/roles', label: (item) => item.name },
  companies: { endpoint: '/crm/companies', label: (item) => item.name },
  contacts: { endpoint: '/crm/contacts', label: (item) => `${item.first_name} ${item.last_name ?? ''}`.trim() },
  leads: { endpoint: '/crm/leads', label: (item) => item.name },
  employees: { endpoint: '/hr/employees', label: (item) => `${item.employee_code} · ${item.first_name} ${item.last_name ?? ''}`.trim() },
  departments: { endpoint: '/hr/departments', label: (item) => item.name },
  projects: { endpoint: '/projects/projects', label: (item) => `${item.code} · ${item.name}` },
  salesOrders: { endpoint: '/sales/orders', label: (item) => `${item.order_number} · ${item.status}` },
  requisitions: { endpoint: '/procurement/requisitions', label: (item) => item.requisition_number },
  purchaseOrders: { endpoint: '/procurement/purchase-orders', label: (item) => item.po_number },
  permissions: { endpoint: '/roles/permissions/catalog', label: (item) => item.code },
  bankAccounts: { endpoint: '/finance/bank-accounts', label: (item) => `${item.bank_name} · ${item.account_number}` },
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
