import { useEffect, useRef, useState, type ReactNode } from 'react'

/** Renders `children` only once the placeholder has come within `margin` of the viewport, then keeps them mounted.
 *  Keeps a heavy WebGL scene lower on the page from competing with the hero globe for the GPU on first paint. */
export function WhenNear({ children, margin = '500px', className = '' }: { children: ReactNode; margin?: string; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [near, setNear] = useState(() => typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    const el = ref.current
    if (!el || near) return
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setNear(true); io.disconnect() }
    }, { rootMargin: margin })
    io.observe(el)
    return () => io.disconnect()
  }, [near, margin])
  return <div ref={ref} className={className}>{near ? children : null}</div>
}
