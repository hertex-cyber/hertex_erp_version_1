import test from 'node:test'
import assert from 'node:assert/strict'

import { idempotencyKeyFor, normalizeIdempotencyPayload } from '../src/lib/api.js'

test('idempotency payload normalisation is stable and drops volatile fields', () => {
  const first = normalizeIdempotencyPayload({ b: 2, a: 1, csrf_token: 'x', nested: { z: 3, y: 4 } })
  const second = normalizeIdempotencyPayload({ nested: { y: 4, z: 3 }, a: 1, b: 2, csrf_token: 'different' })
  assert.deepEqual(first, second)
  assert.equal('csrf_token' in first, false)
})

test('idempotency keys are stable across retries and volatile reversal references', () => {
  const first = idempotencyKeyFor({
    method: 'post',
    url: '/projects/ai/actions/7/execute',
    data: { decision: 'approve', reversal_reference: 'ui:one' },
  }, 'test-salt')
  const second = idempotencyKeyFor({
    method: 'POST',
    url: '/projects/ai/actions/7/execute',
    data: { reversal_reference: 'ui:two', decision: 'approve' },
  }, 'test-salt')
  assert.equal(first, second)
  assert.match(first, /^pm-[0-9a-f]{8}-[0-9a-f]{8}$/)
})

test('idempotency keys differ for distinct mutation payloads', () => {
  const first = idempotencyKeyFor({ method: 'post', url: '/projects/ai/actions', data: { action: 'approve' } }, 'test-salt')
  const second = idempotencyKeyFor({ method: 'post', url: '/projects/ai/actions', data: { action: 'reject' } }, 'test-salt')
  assert.notEqual(first, second)
})
