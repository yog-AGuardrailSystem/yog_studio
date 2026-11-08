/** Endless scrolling row of chips. Pauses on hover; static under reduced motion (CSS). */
export function Marquee({ items }: { items: string[] }) {
  const row = (
    <div className="marquee-track" aria-hidden>
      {items.map((t, i) => (
        <span key={`${t}-${i}`} className="whitespace-nowrap rounded-full border border-slate-700 bg-slate-900/60 px-4 py-1.5 font-mono text-sm text-sky-200">
          {t}
        </span>
      ))}
    </div>
  )
  return (
    <div className="marquee" data-testid="marquee">
      <span className="sr-only">Tools from the sample agents: {items.join(', ')}</span>
      {row}
      {row}
    </div>
  )
}
