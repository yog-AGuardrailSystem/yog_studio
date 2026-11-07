import { useEffect, useState } from 'react'
import { getJson } from '../api/client'

/** Shows a banner when the backend can't be reached. Wording differs for local dev vs the hosted site. */
export function StatusBar() {
  const [up, setUp] = useState<boolean | null>(null)

  useEffect(() => {
    let alive = true
    const ping = () =>
      getJson<{ status: string }>('/health')
        .then(() => alive && setUp(true))
        .catch(() => alive && setUp(false))
    void ping()
    const t = setInterval(ping, 5000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  if (up !== false) return null
  return (
    <div className="mb-4 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900" role="alert" data-testid="backend-down">
      {import.meta.env.DEV ? (
        <>
          Cannot reach the backend. Start it with <code>.\scripts\dev.ps1</code> (or see docs/RUNNING.md). This page retries automatically.
        </>
      ) : (
        <>The server is waking up. On the free hosting tier this can take about 30 seconds. This page retries automatically.</>
      )}
    </div>
  )
}
