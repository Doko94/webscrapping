function renderValue(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') return value.toLocaleString('es-CL')
  return String(value)
}

export default function DataTable({ columns, rows, emptyMessage = 'Sin datos disponibles.' }) {
  if (!rows?.length) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center text-sm text-muted">
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              {columns.map((column) => (
                <th key={column.key} className="whitespace-nowrap px-4 py-3 text-left font-semibold text-slate-700">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {rows.map((row, index) => (
              <tr key={`${row.sku ?? row.name ?? row.supermarket ?? 'row'}-${index}`} className="hover:bg-slate-50">
                {columns.map((column) => (
                  <td key={column.key} className="max-w-[360px] px-4 py-3 align-top text-slate-700">
                    {column.render ? column.render(row[column.key], row) : renderValue(row[column.key])}
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

