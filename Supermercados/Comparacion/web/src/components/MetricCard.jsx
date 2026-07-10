export default function MetricCard({ label, value, helper }) {
  return (
    <article className="rounded-2xl border border-[#ead9d7] bg-white/90 p-5 shadow-soft">
      <p className="text-sm font-semibold text-plum">{label}</p>
      <p className="mt-2 text-3xl font-bold tracking-tight text-ink">{value}</p>
      {helper ? <p className="mt-2 text-sm text-muted">{helper}</p> : null}
    </article>
  )
}
