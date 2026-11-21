import { test, expect } from '@playwright/test'

const CREDENTIALS = { email: 'admin@hertex.dev', password: 'Admin@12345' }
const API_PREFIX = '/api/v1'
const SECRET_KEY = 'gst_portal.client_id'
let apiContext
let token = ''

async function apiFetch(path, init = {}) {
  const headers = { Accept: 'application/json', ...(init.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await apiContext.fetch(`${API_PREFIX}${path}`, { ...init, headers })
  if (!response.ok()) {
    throw new Error(`${path} failed with ${response.status()}: ${await response.text()}`)
  }
  return response
}

async function apiJson(path, init = {}) {
  return (await apiFetch(path, init)).json()
}

async function login(page) {
  await page.goto('/login')
  await page.getByPlaceholder('you@company.com').fill(CREDENTIALS.email)
  await page.getByPlaceholder('••••••••').fill(CREDENTIALS.password)
  await page.getByRole('button', { name: /sign in|login/i }).click()
  await expect(page).not.toHaveURL(/\/login$/)
  await page.waitForLoadState('networkidle')
}

test.beforeAll(async ({ playwright, baseURL }) => {
  apiContext = await playwright.request.newContext({ baseURL })
  const response = await apiContext.post(`${API_PREFIX}/auth/login`, { data: CREDENTIALS })
  expect(response.ok(), await response.text()).toBeTruthy()
  const body = await response.json()
  token = body.access_token
})

test.afterAll(async () => {
  token = ''
  await apiContext?.dispose()
})

test('numbering preview allocates the same document number', async ({ page }) => {
  test.setTimeout(90000)
  await login(page)
  await page.goto('/settings/numbering')
  await expect(page.getByTestId('numbering-page')).toBeVisible()

  const salesOrderRow = page.getByTestId('sequence-row-sales_order')
  await salesOrderRow.getByTestId('sequence-preview-sales_order').click()
  const preview = await page.getByTestId('sequence-preview-value').getAttribute('data-preview-value')
  expect(preview).toBeTruthy()

  await salesOrderRow.getByTestId('sequence-status-sales_order').click()
  const statusDrawer = page.getByTestId('sequence-status-drawer')
  await expect(statusDrawer).toBeVisible()
  await expect(page.getByTestId('status-preview')).toHaveText(preview)
  await statusDrawer.getByRole('button', { name: 'Close status' }).last().click()

  const products = await apiJson('/inventory/products?size=1')
  const product = products.items?.[0]
  expect(product?.id).toBeTruthy()

  const orderDate = new Date().toISOString().slice(0, 10)
  const order = await apiJson('/sales/orders', {
    method: 'POST',
    data: {
      order_date: orderDate,
      lines: [{ product_id: product.id, quantity: 1, unit_price: 100, tax_rate: 0 }],
    },
  })
  expect(order.order_number).toBe(preview)
})

test('typed setting change drives invoice terms and is auditable with secret rotation', async ({ page }) => {
  test.setTimeout(120000)
  const dueDays = 45
  const issueDate = new Date().toISOString().slice(0, 10)
  const due = new Date(`${issueDate}T00:00:00Z`)
  due.setUTCDate(due.getUTCDate() + dueDays)
  const dueDate = due.toISOString().slice(0, 10)

  await login(page)
  await page.goto('/settings/values')
  await page.getByTestId('settings-search').fill('finance.invoice.due_days')
  const field = page.getByTestId('settings-field-finance.invoice.due_days')
  await expect(field).toBeVisible()
  await field.getByTestId('setting-input-finance.invoice.due_days').fill(String(dueDays))
  await field.getByTestId('setting-reason-finance.invoice.due_days').fill('E2E due-date verification')
  await field.getByTestId('setting-save-finance.invoice.due_days').click()
  await expect(field.getByTestId('setting-state-finance.invoice.due_days')).toHaveText(/Saved|Awaiting approval/)

  const setting = await apiJson('/settings/values/finance.invoice.due_days')
  expect(setting.value).toBe(dueDays)

  const invoice = await apiJson('/finance/invoices', {
    method: 'POST',
    data: {
      issue_date: issueDate,
      due_date: dueDate,
      subtotal: 100,
      tax: 0,
      total: 100,
      currency: 'INR',
      notes: 'E2E due-date verification',
    },
  })
  expect(invoice.due_date).toBe(dueDate)

  await page.goto('/settings/history?key=finance.invoice.due_days')
  await expect(page.getByTestId('history-timeline')).toContainText(String(dueDays))

  const secrets = await apiJson('/settings/secrets')
  const existing = secrets.find((row) => row.key === SECRET_KEY)
  if (!existing) {
    await apiFetch(`/settings/secrets/${SECRET_KEY}`, {
      method: 'PUT',
      data: { value: `e2e-setup-${Date.now()}`, reason: 'E2E secret rotation setup' },
    })
  } else if (['pending', 'rotating'].includes(existing.status)) {
    await apiFetch(`/settings/secrets/${SECRET_KEY}/commit`, { method: 'POST' })
  }

  await page.goto('/settings/secrets')
  const secretRow = page.getByTestId(`secret-row-${SECRET_KEY}`)
  await expect(secretRow).toBeVisible()
  await secretRow.getByTestId(`secret-rotate-${SECRET_KEY}`).click()
  await page.getByTestId('secret-value').fill(`e2e-rotate-${Date.now()}`)
  await page.getByTestId('secret-action-submit').click()
  await expect(secretRow).toContainText(/pending|active/i)

  const audits = await apiJson('/system/audit-logs?module=settings&action=settings.secret.rotate&size=20')
  expect(audits.items.some((item) => item.changes?.key === SECRET_KEY)).toBeTruthy()

  await page.goto(`/settings/history?key=${SECRET_KEY}`)
  await expect(page.getByTestId('history-timeline')).toContainText('settings.secret.rotate')

  const latest = await apiJson('/settings/secrets')
  const rotated = latest.find((row) => row.key === SECRET_KEY)
  if (rotated && ['pending', 'rotating'].includes(rotated.status)) {
    await apiFetch(`/settings/secrets/${SECRET_KEY}/commit`, { method: 'POST' })
  }
})

test('settings smoke across desktop and 390px viewports', async ({ page }) => {
  test.setTimeout(120000)
  await login(page)
  const paths = [
    '/settings',
    '/settings/organisation',
    '/settings/localisation',
    '/settings/modules',
    '/settings/values',
    '/settings/numbering',
    '/settings/numbering/gaps',
    '/settings/numbering/blocks',
    '/settings/secrets',
    '/settings/history',
  ]

  async function assertNoOverflow() {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    expect(overflow, `horizontal overflow at ${page.url()}`).toBeLessThanOrEqual(1)
  }

  for (const path of paths) {
    await page.goto(path)
    await expect(page.locator('h1').first()).toBeVisible()
    await assertNoOverflow()
  }

  await page.setViewportSize({ width: 390, height: 844 })
  for (const path of paths) {
    await page.goto(path)
    await expect(page.locator('h1').first()).toBeVisible()
    await assertNoOverflow()
  }
})
