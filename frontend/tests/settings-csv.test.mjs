import test from 'node:test'
import assert from 'node:assert/strict'
import { escapeCsvCell, toCsv } from '../src/components/settings/csv.js'

test('escapeCsvCell neutralises spreadsheet formulas and quotes delimiters', () => {
  assert.equal(escapeCsvCell(null), '')
  assert.equal(escapeCsvCell(undefined), '')
  assert.equal(escapeCsvCell('=1+1'), "'=1+1")
  assert.equal(escapeCsvCell('+CMD'), "'+CMD")
  assert.equal(escapeCsvCell('@SUM(A1)'), "'@SUM(A1)")
  assert.equal(escapeCsvCell('a,b'), '"a,b"')
  assert.equal(escapeCsvCell('a"b'), '"a""b"')
  assert.equal(escapeCsvCell('a\nb'), '"a\nb"')
  assert.equal(escapeCsvCell({ status: 'ok' }), '"{""status"":""ok""}"')
})

test('toCsv emits a BOM, header labels and transformed values', () => {
  const csv = toCsv(
    [{ key: 'finance.invoice.due_days', value: 30, note: 'one, two' }],
    [
      { key: 'key', label: 'Setting key' },
      { key: 'value', label: 'Value' },
      { key: 'note', label: 'Note' },
      { key: 'unused', label: 'Source' },
    ],
  )
  assert.ok(csv.startsWith('\uFEFF'))
  assert.match(csv, /Setting key,Value,Note,Source/)
  assert.match(csv, /finance\.invoice\.due_days,30,"one, two",/)
  assert.ok(csv.endsWith('\r\n'))
})

test('toCsv supports computed columns', () => {
  const csv = toCsv(
    [{ before: 15, after: 30 }],
    [{ key: 'change', label: 'Change', value: (row) => `${row.before} → ${row.after}` }],
  )
  assert.match(csv, /15 → 30/)
})
