import { test, expect } from '@playwright/test'

const CREDENTIALS = { email: 'admin@hertex.dev', password: 'Admin@12345' }

const ROUTES = [
  ['/crm/inbox', 'Unified inbox'],
  ['/crm/calls', 'Calls'],
  ['/crm/call-assessments', 'Call assessments'],
  ['/crm/social/accounts', 'Social accounts'],
  ['/crm/social/posts', 'Social publishing'],
  ['/crm/pipeline-report', 'Pipeline report'],
]

test('CRM workflow screens open instead of falling through to 404', async ({ page }) => {
  test.setTimeout(120000)
  await page.goto('/login')
  await page.getByPlaceholder('you@company.com').fill(CREDENTIALS.email)
  await page.getByPlaceholder('••••••••').fill(CREDENTIALS.password)
  await page.getByRole('button', { name: /sign in|login/i }).click()
  await expect(page).not.toHaveURL(/\/login$/)
  await page.waitForLoadState('networkidle')

  for (const [path, heading] of ROUTES) {
    await page.goto(path)
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: '404', exact: true })).toHaveCount(0)
  }
})
