export function escapeCsvCell(value) {
  if (value === null || value === undefined) return ''
  let text = typeof value === 'object' ? JSON.stringify(value) : String(value)
  if (/^[=+@\t\r]/.test(text)) text = `'${text}`
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

export function toCsv(rows = [], columns = []) {
  const lines = [columns.map((column) => escapeCsvCell(column.label ?? column.key)).join(',')]
  for (const row of rows) {
    lines.push(
      columns
        .map((column) =>
          escapeCsvCell(typeof column.value === 'function' ? column.value(row) : row?.[column.key]),
        )
        .join(','),
    )
  }
  return `\uFEFF${lines.join('\r\n')}\r\n`
}

export function downloadCsv(filename, content) {
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
