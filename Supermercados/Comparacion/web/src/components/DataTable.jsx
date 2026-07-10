function renderValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') return value.toLocaleString('es-CL')
  return String(value)
}

function renderCell(column, row) {
  return column.render ? column.render(row[column.key], row) : renderValue(row[column.key])
}

export default function DataTable({ columns, rows, emptyMessage = 'Sin datos disponibles.' }) {
  if (!rows?.length) {
    return (
      <div className="rounded-2xl border border-dashed border-[#d9c7ca] bg-[#fbf7f4] p-8 text-center text-sm text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-[#ead9d7]">
      <div className="divide-y divide-[#f1e2df] bg-white md:hidden">
        {rows.map((row, index) => {
          const primaryColumn = columns.find((column) => column.primary) ?? columns[0]
          const visibleColumns = columns.filter((column) => column.mobile !== false && column.key !== primaryColumn.key)

          return (
            <article key={`${row.sku ?? row.name ?? row.supermarket ?? 'row'}-card-${index}`} className="p-4">
              <div className="mb-3 text-base font-bold text-ink">
                {renderCell(primaryColumn, row)}
              </div>
              <dl className="space-y-3">
                {visibleColumns.map((column) => (
                  <div key={column.key} className={column.compact === false ? 'grid gap-1' : 'grid grid-cols-[96px_1fr] gap-3'}>
                    <dt className="text-[11px] font-bold uppercase tracking-wide text-muted">{column.label}</dt>
                    <dd className="min-w-0 text-sm leading-snug text-slate-700">{renderCell(column, row)}</dd>
                  </div>
                ))}
              </dl>
            </article>
          )
        })}
      </div>

      <div className="overflow-x-auto">
        <table className="hidden min-w-full divide-y divide-[#ead9d7] text-sm md:table">
          <thead className="bg-[#fbf0ed]">
            <tr>
              {columns.map((column) => (
                <th key={column.key} className="whitespace-nowrap px-4 py-3 text-left font-semibold text-slate-700">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#f1e2df] bg-white">
            {rows.map((row, index) => (
              <tr key={`${row.sku ?? row.name ?? row.supermarket ?? 'row'}-${index}`} className="hover:bg-slate-50">
                {columns.map((column) => (
                  <td key={column.key} className="max-w-[360px] px-4 py-3 align-top text-slate-700">
                    {renderCell(column, row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
