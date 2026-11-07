import { useEffect, useState } from 'react'

/** true at >= 1024px (Tailwind lg). Used to switch between a sticky side visual and inline visuals. */
export function useIsDesktop() {
  const q = '(min-width: 1024px)'
  const [v, setV] = useState(() => (typeof window === 'undefined' ? true : window.matchMedia(q).matches))
  useEffect(() => {
    const m = window.matchMedia(q)
    const h = () => setV(m.matches)
    m.addEventListener('change', h)
    return () => m.removeEventListener('change', h)
  }, [])
  return v
}
