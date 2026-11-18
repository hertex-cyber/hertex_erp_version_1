import test from 'node:test'
import assert from 'node:assert/strict'

import {
  AI_ACTION_TYPES,
  PROJECT_ASSISTANT_PROMPTS,
  aiActionScope,
  earnedValue,
  filterReportRows,
  isProhibitedAiAction,
  scopedProjectQuestion,
  topFeatures,
} from '../src/lib/project-helpers.js'

test('topFeatures returns the three strongest features in order', () => {
  const result = topFeatures({ delay_days: 4, burn_rate: 9.5, velocity: 1, blockers: 7 })
  assert.deepEqual(result.map(([name]) => name), ['burn_rate', 'blockers', 'delay_days'])
  assert.equal(result[0][1], 9.5)
})

test('prohibited AI actions are blocked from execution controls', () => {
  assert.equal(isProhibitedAiAction({ action_type: 'draft_status_update' }), false)
  assert.equal(isProhibitedAiAction({ proposed_json: { action: 'auto_close_work_item' } }), true)
  assert.equal(isProhibitedAiAction({ proposed_json: { actions: [{ type: 'POST_INVOICE' }] } }), true)
})

test('AI action scope is readable', () => {
  assert.equal(aiActionScope({ proposed_json: { scope: { project_id: 'p1' } } }), '{"project_id":"p1"}')
  assert.equal(aiActionScope({}), '—')
})

test('earned value produces EAC and non-negative ETC', () => {
  assert.deepEqual(earnedValue({ budget: 100, cost: 40, earned_value: 50, cpi: 0.8 }), { eac: 125, etc: 85 })
  assert.deepEqual(earnedValue({ budget: 100, cost: 40, earned_value: 50, cpi: 0 }), { eac: 90, etc: 50 })
})

test('report filters respect project, employee and date rows', () => {
  const rows = [
    { project_id: 'p1', employee_id: 'e1', week_start: '2026-01-05' },
    { project_id: 'p2', employee_id: 'e1', week_start: '2026-02-05' },
    { project_id: 'p1', employee_id: 'e2', week_start: '2026-03-05' },
  ]
  assert.equal(filterReportRows(rows, { projectId: 'p1' }).length, 2)
  assert.equal(filterReportRows(rows, { team: 'e1' }).length, 2)
  assert.equal(filterReportRows(rows, { dateFrom: '2026-02-01', dateTo: '2026-02-28' }).length, 1)
})

test('assistant exposes all nine project intents and scopes prompts to the selected project', () => {
  assert.equal(PROJECT_ASSISTANT_PROMPTS.length, 9)
  assert.ok(AI_ACTION_TYPES.includes('draft_billing_run'))
  assert.equal(
    scopedProjectQuestion('What is the critical path?', { name: 'Apollo', code: 'AP' }),
    'What is the critical path for project Apollo',
  )
  assert.equal(scopedProjectQuestion('Critical path for Apollo', { name: 'Apollo' }), 'Critical path for Apollo')
  assert.equal(scopedProjectQuestion('Critical path', null), 'Critical path')
})
