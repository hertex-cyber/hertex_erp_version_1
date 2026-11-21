import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

const externalSource = read('../src/pages/finance/ExternalIntegrationsPage.jsx')
const ocrSource = read('../src/pages/finance/OcrInboxPage.jsx')
const appSource = read('../src/App.jsx')
const navSource = read('../src/lib/nav.js')

test('external integration screen calls every provider credential endpoint', () => {
  assert.match(externalSource, /api\.get\('\/integrations\/external\/providers'\)/)
  assert.match(externalSource, /\/integrations\/external\/providers\/\$\{[^}]+\}\/credentials`/)
  assert.match(externalSource, /\/credentials\/\$\{[^}]+\}\/rotate`/)
  assert.match(externalSource, /\/credentials\/\$\{[^}]+\}\/commit`/)
  assert.match(externalSource, /\/credentials\/\$\{[^}]+\}\/rollback`/)
  assert.match(externalSource, /\/integrations\/external\/providers\/\$\{[^}]+\}\/test-connection`/)
})

test('external integration screen keeps secrets write-only and records last test result', () => {
  assert.match(externalSource, /type="password"/)
  assert.match(externalSource, /autoComplete="new-password"/)
  assert.match(externalSource, /setSecretValue\(''\)/)
  assert.match(externalSource, /Last test result/)
  assert.match(externalSource, /TEST_RESULTS_KEY/)
  assert.match(externalSource, /reason: reason\.trim\(\)/)
})

test('ocr inbox calls document, draft and review endpoints', () => {
  assert.match(ocrSource, /api\.post\('\/procurement\/ocr\/documents'/)
  assert.match(ocrSource, /api\.post\('\/procurement\/ocr\/documents\/upload'/)
  assert.match(ocrSource, /api\.get\('\/procurement\/ocr\/drafts'/)
  assert.match(ocrSource, /\/procurement\/ocr\/drafts\/\$\{draft\.id\}`/)
  assert.match(ocrSource, /\/procurement\/ocr\/drafts\/\$\{confirmTarget\.id\}\/confirm`/)
  assert.match(ocrSource, /\/procurement\/ocr\/drafts\/\$\{rejectTarget\.id\}\/reject`/)
  assert.match(ocrSource, /api\.delete\(`\/procurement\/ocr\/drafts\/\$\{draft\.id\}`\)/)
})

test('ocr inbox requires vendor_id and reason and shows confidence and status', () => {
  assert.match(ocrSource, /vendor_id: confirmForm\.vendor_id/)
  assert.match(ocrSource, /Select a vendor before confirming this OCR draft\./)
  assert.match(ocrSource, /reason: reason\.trim\(\)/)
  assert.match(ocrSource, /confidence/)
  assert.match(ocrSource, /<Badge>\{row\.status\}<\/Badge>/)
})

test('new screens are lazy loaded and routed', () => {
  assert.match(appSource, /import\('\.\/pages\/finance\/ExternalIntegrationsPage'\)/)
  assert.match(appSource, /import\('\.\/pages\/finance\/OcrInboxPage'\)/)
  assert.ok(appSource.includes('path="/finance/external-integrations"'))
  assert.ok(appSource.includes('path="/finance/ocr-inbox"'))
  assert.ok(appSource.includes('path="/procurement/ocr-inbox"'))
})

test('navigation exposes the new screens with existing permissions', () => {
  assert.ok(navSource.includes("to: '/finance/external-integrations'"))
  assert.ok(navSource.includes("permission: 'integrations.channel.manage'"))
  assert.ok(navSource.includes("to: '/finance/ocr-inbox'"))
  assert.ok(navSource.includes("permission: 'procurement.vendorinvoice.read'"))
})
