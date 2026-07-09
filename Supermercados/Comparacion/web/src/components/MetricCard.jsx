export default function MetricCard({ label, value, helper }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-soft">
      <p className="text-sm font-medium text-muted">{label}</p>
      <p className="mt-2 text-3xl font-bold tracking-tight text-ink">{value}</p>
      {helper ? <p className="mt-2 text-sm text-muted">{helper}</p> : null}
    </article>
  )
}

