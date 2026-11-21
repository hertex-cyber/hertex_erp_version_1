import { test, expect } from '@playwright/test'

const CREDENTIALS = { email: 'admin@hertex.dev', password: 'Admin@12345' }
const API_PREFIX = '/api/v1'
const PASSWORD = 'Quartz!Maple#R8v'

test('role menu access controls sidebar links and direct navigation', async ({ page, playwright, baseURL }) => {
  test.setTimeout(120000)
  const api = await playwright.request.newContext({ baseURL })
  const admin = await api.post(`${API_PREFIX}/auth/login`, { data: CREDENTIALS })
  expect(admin.ok(), await admin.text()).toBeTruthy()
  const adminHeaders = { Authorization: `Bearer ${(await admin.json()).access_token}` }

  const marker = Date.now().toString(36)
  const permissionsResponse = await api.get(`${API_PREFIX}/roles/permissions/catalog`, { headers: adminHeaders })
  expect(permissionsResponse.ok()).toBeTruthy()
  const permission = (await permissionsResponse.json()).find((item) => item.code === 'crm.company.read')
  expect(permission?.id).toBeTruthy()

  const roleResponse = await api.post(`${API_PREFIX}/roles`, {
    headers: adminHeaders,
    data: {
      name: `CRM menu ${marker}`,
      slug: `crm-menu-${marker}`,
      menu_keys: ['crm'],
      permission_ids: [permission.id],
    },
  })
  expect(roleResponse.ok(), await roleResponse.text()).toBeTruthy()
  const role = await roleResponse.json()

  const email = `menu-${marker}@example.com`
  const userResponse = await api.post(`${API_PREFIX}/users`, {
    headers: adminHeaders,
    data: {
      email,
      password: PASSWORD,
      full_name: 'Menu Access User',
      role_ids: [role.id],
    },
  })
  expect(userResponse.ok(), await userResponse.text()).toBeTruthy()
  await api.dispose()

  await page.goto('/login')
  await page.getByPlaceholder('you@company.com').fill(email)
  await page.getByPlaceholder('••••••••').fill(PASSWORD)
  await page.getByRole('button', { name: /sign in|login/i }).click()
  await expect(page).not.toHaveURL(/\/login$/)

  await page.goto('/crm/companies')
  await expect(page.getByRole('link', { name: 'Companies' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Finance overview' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Team', exact: true })).toHaveCount(0)

  await page.goto('/finance')
  await expect(page.getByTestId('access-denied')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Access denied' })).toBeVisible()
})
