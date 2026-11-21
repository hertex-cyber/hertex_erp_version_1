import { Download } from 'lucide-react'
import { downloadCsv, toCsv } from './csv'

export default function CsvExportButton({
  filename = 'settings-report.csv',
  rows = [],
  columns = [],
  label = 'Export CSV',
  testId = 'csv-export',
  disabled = false,
}) {
  return (
    <button
      type="button"
      className="btn-secondary w-full sm:w-auto"
      data-testid={testId}
      disabled={disabled || !rows.length}
      onClick={() => downloadCsv(filename, toCsv(rows, columns))}
    >
      <Download size={15} />
      {label}
    </button>
  )
}
