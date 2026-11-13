import { useAiMode } from '../lib/aiMode'

/** Which YOG engine made the decisions on this page (from /info). Nothing is shown until the server has said. */
export function EngineBadge({ className = '' }: { className?: string }) {
  const { info } = useAiMode()
  if (!info?.engine) return null
  const c = info.engine === 'c'
  return (
    <span className={`chip ${className}`} data-testid="engine-badge"
      title={c ? `${info.engine_roles ?? ''}${info.engine_commit ? ` · yog_engine ${info.engine_commit}` : ''}` : 'The Python reference engine (engine/yog.py)'}>
      {c ? 'Decided by the C engine' : 'Decided by the Python reference'}
    </span>
  )
}
