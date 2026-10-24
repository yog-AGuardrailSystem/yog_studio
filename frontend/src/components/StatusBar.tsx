import { useEffect, useState } from 'react'
import { getJson } from '../api/client'
import { useAppState } from '../state'

/** Backend health banner + a 4-step progress strip (upload -> rules -> approve -> run). */
export function StatusBar() {
  const { analysis, draft, approved } = useAppState()
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

  const steps = [
    ['1 Upload', !!analysis],
    ['2 Rules', !!draft],
    ['3 Approved', !!approved],
  ] as const

  return (
    <div className="mb-4 space-y-2">
      {up === false && (
        <div className="rounded border border-red-300 bg-red-50 p-2 text-sm text-red-800" role="alert" data-testid="backend-down">
          Cannot reach the backend. Start it with <code>.\scripts\dev.ps1</code> (or see docs/RUNNING.md). This page retries automatically.
        </div>
      )}
      <div className="flex gap-2 text-xs" data-testid="progress">
        {steps.map(([label, done]) => (
          <span key={label} className={`rounded-full border px-3 py-1 ${done ? 'border-green-300 bg-green-100 text-green-800' : 'border-slate-200 bg-white text-slate-500'}`}>
            {done ? '✓ ' : ''}{label}
          </span>
        ))}
      </div>
    </div>
  )
}
