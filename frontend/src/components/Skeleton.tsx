/** Grey pulsing placeholder block for content that is loading. */
export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton rounded ${className}`} aria-hidden />
}
