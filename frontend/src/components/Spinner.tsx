/** Small inline spinner. Announces `label` to screen readers. */
export function Spinner({ label = 'Loading', className = '' }: { label?: string; className?: string }) {
  return (
    <span role="status" className={`inline-flex items-center gap-2 ${className}`}>
      <span className="spinner" aria-hidden />
      <span className="sr-only">{label}</span>
    </span>
  )
}
