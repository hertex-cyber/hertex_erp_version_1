import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('CRM workflow routes are reachable from the app', () => {
  const source = read('../src/App.jsx')
  for (const path of [
    '/crm/inbox',
    '/crm/calls',
    '/crm/call-assessments',
    '/crm/social/accounts',
    '/crm/social/posts',
    '/crm/pipeline-report',
  ]) {
    assert.match(source, new RegExp(`path="${path.replaceAll('/', '\\/')}"`))
  }
})

test('CRM navigation exposes workflow surfaces with matching permissions', () => {
  const source = read('../src/lib/nav.js')
  const items = [
    "to: '/crm/inbox', icon: Inbox, permission: 'crm.inbox.read'",
    "to: '/crm/calls', icon: MessageSquare, permission: 'crm.call.read'",
    "to: '/crm/call-assessments', icon: Sparkles, permission: 'crm.call.read'",
    "to: '/crm/social/accounts', icon: Send, permission: 'crm.socialaccount.read'",
    "to: '/crm/social/posts', icon: Megaphone, permission: 'crm.socialpost.read'",
    "to: '/crm/pipeline-report', icon: BarChart3, permission: 'crm.report.read'",
  ]
  for (const item of items) assert.ok(source.includes(item), `missing nav item: ${item}`)
})

test('lead score is read-only and workflow actions use the canonical endpoints', () => {
  const source = read('../src/pages/resources/crm.jsx')
  assert.doesNotMatch(source, /name: 'score'/)
  assert.match(source, /row\.score_grade/)
  for (const endpoint of [
    '/crm/leads/${row.id}/rescore',
    '/crm/leads/${row.id}/convert',
    '/crm/deals/${row.id}/win',
    '/crm/calls/${row.id}/assess',
    '/crm/social/posts/${row.id}/approve',
    '/crm/social/posts/${row.id}/publish',
    '/crm/reports/pipeline',
  ]) {
    assert.ok(source.includes(endpoint), `missing endpoint: ${endpoint}`)
  }
})
