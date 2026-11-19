import { cn } from "../lib/format";

import { EmptyState, Spinner } from "./ui";

export function DataTable({
  columns,
  rows,
  loading,
  empty,
  rowActions,
  onRowClick,
  rowKey = (row) => row.id,
}) {
  if (loading) {
    return (
      <div className="flex items-center justify-center gap-3 px-5 py-20 text-sm text-muted">
        <Spinner className="h-5 w-5 text-primary" />
        Loading records…
      </div>
    );
  }

  if (!rows.length) return empty;

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse">
        <thead className="border-b border-line bg-surface-2/70">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={cn(
                  "th",
                  column.align === "right" && "text-right",
                  column.className,
                )}
              >
                {column.label}
              </th>
            ))}
            {rowActions && <th className="th text-right">Actions</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              className={cn(
                "border-b border-line/70 transition last:border-0 hover:bg-surface-2/60",
                onRowClick && "cursor-pointer",
              )}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cn(
                    "td",
                    column.align === "right" && "text-right",
                    column.className,
                  )}
                  onClick={
                    column.stopPropagation
                      ? (event) => event.stopPropagation()
                      : undefined
                  }
                >
                  {column.render
                    ? column.render(row)
                    : (row[column.key] ?? "—")}
                </td>
              ))}
              {rowActions && (
                <td
                  className="td text-right"
                  onClick={(event) => event.stopPropagation()}
                >
                  <div className="flex items-center justify-end gap-1">
                    {rowActions(row)}
                  </div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TableSkeleton({ rows = 6 }) {
  return (
    <div className="divide-y divide-line">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="flex items-center gap-4 px-5 py-4">
          <div className="shimmer h-9 w-9 rounded-full" />
          <div className="flex-1 space-y-2">
            <div className="shimmer h-3 w-1/3 rounded" />
            <div className="shimmer h-3 w-1/5 rounded" />
          </div>
          <div className="shimmer h-6 w-16 rounded-full" />
        </div>
      ))}
    </div>
  );
}

export { EmptyState };
