import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('all sixteen plan report endpoints are wired literally', () => {
  const source = read('../src/pages/resources/projects-reports.jsx')
  const endpoints = [
    'health',
    'budget_vs_actual',
    'earned_value',
    'utilisation',
    'workload',
    'unbilled_wip',
    'billing_leakage',
    'velocity',
    'cycle_lead_time',
    'cumulative_flow',
    'throughput_rework',
    'risk_heatmap',
    'milestone_schedule',
    'timesheet_compliance',
    'portfolio_benefits',
    'ai_governance',
  ]
  for (const key of endpoints) {
    assert.ok(source.includes(`'/projects/reports/${key}'`), `missing endpoint for ${key}`)
  }
})

test('governance is reachable from navigation, reports and the assistant', () => {
  assert.match(read('../src/lib/nav.js'), /report=ai_governance/)
  assert.match(read('../src/pages/resources/projects-reports.jsx'), /AI review queue/)
  assert.match(read('../src/pages/Assistant.jsx'), /AI governance/)
})

test('AI execution UI keeps human control and blocks prohibited actions', () => {
  const source = read('../src/pages/resources/projects.jsx')
  assert.match(source, /isProhibitedAiAction\(row\)/)
  assert.match(source, /reversal_reference/)
  assert.match(source, /on_behalf_of_id/)
  assert.match(source, /proposed_json/)
})

test('project money surfaces use restricted currency-aware formatting', () => {
  const source = read('../src/pages/resources/projects.jsx')
  assert.match(source, /currency=\{row\.currency \?\? row\.project_currency\} restricted/)
  assert.match(read('../src/components/cells.jsx'), /money\(value, \{ precise, currency, restricted \}\)/)
})
