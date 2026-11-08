/** Animated gradient blobs + faint grid behind a page. Purely decorative. */
export function GlowBackground() {
  return (
    <div className="glow-bg" aria-hidden>
      <div className="blob b1" />
      <div className="blob b2" />
      <div className="blob b3" />
      <div className="grid" />
    </div>
  )
}
