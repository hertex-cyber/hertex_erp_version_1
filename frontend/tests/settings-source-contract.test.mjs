import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

function source(path) {
  return fs.readFileSync(new URL(path, import.meta.url), 'utf8')
}

const values = source('../src/pages/settings/ValuesPage.jsx')
const numbering = source('../src/pages/settings/NumberingPage.jsx')
const gaps = source('../src/pages/settings/GapsPage.jsx')
const blocks = source('../src/pages/settings/BlocksPage.jsx')
const secrets = source('../src/pages/settings/SecretsPage.jsx')
const history = source('../src/pages/settings/HistoryPage.jsx')
const pattern = source('../src/components/settings/PatternBuilder.jsx')
const field = source('../src/components/settings/SettingField.jsx')
const hook = source('../src/components/settings/useSettingValues.js')
const app = source('../src/App.jsx')
const nav = source('../src/lib/nav.js')
const shim = source('../src/pages/resources/settings.jsx')

test('settings UI uses typed registry and preview APIs', () => {
  assert.match(hook, /\/settings\/values/)
  assert.match(field, /\/settings\/values\/\$\{encodeURIComponent\(key\)\}/)
  assert.match(pattern, /\/settings\/sequences\/validate/)
  assert.match(pattern, /\/settings\/sequences\/\$\{encodeURIComponent\(form\.key\)\}\/preview/)
  assert.match(values, /Typed, governed configuration values/)
  assert.match(values, /data-testid="settings-search"/)
  assert.match(values, /<SettingSection/)
})

test('numbering UI exposes fiscal preview, status, locked state and gap controls', () => {
  assert.match(numbering, /Next rendered number/)
  assert.match(numbering, /\/settings\/sequences\/\$\{encodeURIComponent\(row\.key\)\}\/preview/)
  assert.match(numbering, /\/settings\/sequences\/\$\{encodeURIComponent\(editing\.key\)\}/)
  assert.match(numbering, /Locked after first allocation \(SE-14\)/)
  assert.match(numbering, /settings\/numbering\/gaps/)
  assert.match(numbering, /settings\/numbering\/blocks/)
  assert.match(gaps, /\/settings\/reports\/numbering\/gaps/)
  assert.match(blocks, /\/settings\/sequences\/\$\{encodeURIComponent\(key\)\}\/blocks/)
  assert.match(blocks, /\/settings\/blocks\/\$\{returning\.id\}\/return/)
})

test('secrets and history use write-only and audit APIs', () => {
  assert.match(secrets, /\/settings\/secrets/)
  assert.match(secrets, /\/secrets\/\$\{key\}\/rotate/)
  assert.match(secrets, /type="password"/)
  assert.match(secrets, /secret\.mask/)
  assert.match(history, /\/settings\/changes/)
  assert.match(history, /\/system\/audit-logs/)
  assert.match(history, /settings\/changes\/\$\{row\.id\}\/\$\{operation\}/)
})

test('reports expose CSV exports', () => {
  assert.match(gaps, /gaps-csv-export/)
  assert.match(blocks, /blocks-csv-export/)
  assert.match(history, /history-csv-export/)
})

test('settings routes and nav are wired', () => {
  for (const path of [
    '/settings/organisation',
    '/settings/localisation',
    '/settings/modules',
    '/settings/values',
    '/settings/numbering',
    '/settings/numbering/gaps',
    '/settings/numbering/blocks',
    '/settings/secrets',
    '/settings/history',
  ]) {
    assert.ok(app.includes(path), `missing route ${path}`)
  }
  assert.match(nav, /settings\.secret\.manage/)
  assert.match(nav, /system\.audit\.read/)
  assert.match(nav, /settings\.sequence\.read/)
  assert.match(shim, /export \{ default as SettingsValuesPage \}/)
  assert.match(shim, /export \{ default as SequencesPage \}/)
  assert.match(shim, /export function UsersPage/)
  assert.match(shim, /export function RolesPage/)
})
