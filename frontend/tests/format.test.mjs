import test from 'node:test'
import assert from 'node:assert/strict'

import { compactMoney, isRestrictedValue, money, resolveCurrency } from '../src/lib/format.js'

test('restricted values render as Restricted only when masked output is requested', () => {
  assert.equal(isRestrictedValue(null), true)
  assert.equal(isRestrictedValue(' masked '), true)
  assert.equal(money(null, { restricted: true }), 'Restricted')
  assert.equal(money('Restricted', { restricted: true }), 'Restricted')
  assert.equal(money(null), '₹0')
})

test('money and compactMoney honour project currency with safe fallback', () => {
  assert.equal(resolveCurrency('usd'), 'USD')
  assert.equal(resolveCurrency('!!'), 'INR')
  assert.match(money(1234, { currency: 'USD', precise: true }), /\$1,234\.00/)
  assert.equal(compactMoney(250000, { currency: 'INR', restricted: true }), '₹2.50 L')
  assert.equal(compactMoney(undefined, { restricted: true }), 'Restricted')
})
