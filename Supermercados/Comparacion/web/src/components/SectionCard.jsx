export default function SectionCard({ title, description, children, action }) {
  return (
    <section className="rounded-3xl border border-[#ead9d7] bg-white/95 p-5 shadow-soft">
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-xl font-bold text-ink">{title}</h2>
          {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}
