import { test, expect } from '@playwright/test'

const CREDENTIALS = { email: 'admin@hertex.dev', password: 'Admin@12345' }
const API_PREFIX = '/api/v1'
const PASSWORD = 'Quartz!Maple#R8v'

test('team list is scoped to the current workspace by default', async ({ page, playwright, baseURL }) => {
  test.setTimeout(120000)
  const api = await playwright.request.newContext({ baseURL })
  const marker = Date.now().toString(36)
  const email = `scope-${marker}@example.com`
  const registered = await api.post(`${API_PREFIX}/auth/register`, {
    data: {
      email,
      password: PASSWORD,
      full_name: 'Other Workspace User',
      tenant_name: `Other Workspace ${marker}`,
    },
  })
  expect(registered.ok(), await registered.text()).toBeTruthy()

  await page.goto('/login')
  await page.getByPlaceholder('you@company.com').fill(CREDENTIALS.email)
  await page.getByPlaceholder('••••••••').fill(CREDENTIALS.password)
  await page.getByRole('button', { name: /sign in|login/i }).click()
  await expect(page).not.toHaveURL(/\/login$/)

  await page.goto('/settings/users')
  const search = page.getByPlaceholder('Search name, email…')
  await search.fill(email)
  await expect(page.getByText(email)).toHaveCount(0)

  await page.getByRole('combobox').filter({ has: page.locator('option', { hasText: 'All workspaces' }) }).selectOption('all')
  await expect(page.getByText(email)).toBeVisible()

  await api.dispose()
})
