import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { Stepper } from '../components/Stepper'
import { StatusBar } from '../components/StatusBar'
import { useAppState } from '../state'

export default function StudioLayout() {
  const { analysis, draft, approved, reset } = useAppState()
  const navigate = useNavigate()
  const hasWork = !!(analysis || draft || approved)

  function startOver() {
    if (hasWork && !window.confirm('Clear the uploaded agent, your rules, the draft and the approval from this screen and start again?')) return
    reset()
    navigate('/studio')
  }

  return (
    <div className="mx-auto max-w-6xl p-4">
      <header className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-slate-200 pb-3">
        <Link to="/" className="font-display whitespace-nowrap text-xl font-bold text-slate-900" title="Back to the home page">
          YOG<span className="text-brand"> Studio</span>
        </Link>
        <Stepper />
        <div className="ml-auto flex items-center gap-4 text-sm">
          <NavLink to="/check" className={({ isActive }) => (isActive ? 'font-semibold text-sky-800' : 'text-slate-600 hover:text-slate-900')} title="Try a policy against one action, without uploading anything">
            Sandbox
          </NavLink>
          <button type="button" onClick={startOver} className="text-slate-600 hover:text-red-700" data-testid="start-over">
            Start over
          </button>
        </div>
      </header>
      <StatusBar />
      <ErrorBoundary>
        <Outlet />
      </ErrorBoundary>
    </div>
  )
}
