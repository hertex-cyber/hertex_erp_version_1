import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'

import { canNavigate, describePath, featureForMenu, filterNavGroups, menuForPath, NAV_GROUPS } from '../src/lib/nav.js'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

const salesAuth = {
  permissions: ['crm.company.read', 'sales.salesorder.read', 'analytics.dashboard.read'],
  menus: ['dashboard', 'assistant', 'crm', 'sales'],
  featureFlags: {},
  can(code) {
    return this.permissions.includes(code)
  },
  canMenu(key) {
    return this.menus.includes('*') || this.menus.includes(key)
  },
  hasFeature() {
    return true
  },
}

test('navigation descriptors derive the correct module and feature keys', () => {
  assert.equal(menuForPath('/sales/orders'), 'sales')
  assert.equal(menuForPath('/finance/reports?period=q1'), 'finance')
  assert.equal(menuForPath('/settings/security'), 'settings')
  assert.equal(featureForMenu('projects'), 'features.module.projects.enabled')
  assert.equal(describePath('/crm/companies/123').menu, 'crm')
  assert.equal(describePath('/settings/security').permission, null)
})

test('sales role cannot see or open restricted modules', () => {
  const visible = filterNavGroups(NAV_GROUPS, salesAuth)
  const labels = visible.flatMap((group) => group.items.map((item) => item.label))
  assert.ok(labels.includes('Companies'))
  assert.ok(labels.includes('Sales orders'))
  assert.ok(!labels.includes('Finance overview'))
  assert.ok(!labels.includes('Team'))
  assert.equal(canNavigate(describePath('/finance'), salesAuth), false)
  assert.equal(canNavigate(describePath('/hr/employees'), salesAuth), false)
  assert.equal(canNavigate(describePath('/crm/companies'), salesAuth), true)
})

test('explicit false feature flags hide a module even with full menu access', () => {
  const auth = {
    can: () => true,
    canMenu: () => true,
    hasFeature: (key) => key !== 'features.module.projects.enabled',
  }
  assert.equal(canNavigate({ menu: 'projects', feature: 'features.module.projects.enabled' }, auth), false)
  assert.equal(canNavigate({ menu: 'crm' }, auth), true)
})

test('every navigation surface uses the shared access model', () => {
  assert.match(read('../src/components/AppShell.jsx'), /filterNavGroups\(NAV_GROUPS, auth\)/)
  assert.match(read('../src/App.jsx'), /canView\(describePath\(location\.pathname\)\)/)
  assert.match(read('../src/App.jsx'), /data-testid="access-denied"/)
  assert.match(read('../src/components/settings/SettingsSubnav.jsx'), /canView\(describePath\(link\.to\)\)/)
  assert.match(read('../src/pages/settings/SettingsHubPage.jsx'), /canView\(describePath\(card\.to\)\)/)
  assert.match(read('../src/pages/Dashboard.jsx'), /canView\(describePath\(item\.to\)\)/)
  assert.match(read('../src/pages/FinanceDashboard.jsx'), /canView\(describePath\(item\.to\)\)/)
  assert.match(read('../src/pages/Assistant.jsx'), /canView\(describePath\(item\.to\)\)/)
})

test('role administration exposes menu access selection', () => {
  assert.match(read('../src/lib/lookups.js'), /menus: \{ endpoint: '\/roles\/menu\/catalog'/)
  const source = read('../src/pages/resources/settings.jsx')
  assert.match(source, /name: 'menu_keys'.*lookup: 'menus'/)
  assert.match(read('../src/store/auth.js'), /menus: data\.menus \?\? \[\]/)
  assert.match(read('../src/store/auth.js'), /featureFlags: data\.feature_flags \?\? \{\}/)
})

test('brand surfaces use the supplied logo asset', () => {
  assert.ok(existsSync(new URL('../public/logo-transparent-bg.png', import.meta.url)))
  assert.match(read('../src/components/BrandLogo.jsx'), /\/logo-transparent-bg\.png/)
  for (const path of [
    '../src/components/AppShell.jsx',
    '../src/pages/Auth.jsx',
    '../src/App.jsx',
  ]) {
    assert.match(read(path), /BrandLogo/)
    assert.doesNotMatch(read(path), />H</)
  }
  assert.match(read('../index.html'), /rel="icon".*logo-transparent-bg\.png/)
})
