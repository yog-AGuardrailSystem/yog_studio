import { motion, useReducedMotion } from 'motion/react'
import { Link, NavLink, useLocation, useNavigate, useOutlet } from 'react-router-dom'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { Stepper } from '../components/Stepper'
import { StatusBar } from '../components/StatusBar'
import { MotionToggle } from '../lib/motion'
import { useAppState } from '../state'

export default function StudioLayout() {
  const { analysis, draft, approved, reset } = useAppState()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const outlet = useOutlet()
  const reduce = useReducedMotion()
  const hasWork = !!(analysis || draft || approved)

  function startOver() {
    if (hasWork && !window.confirm('Clear the uploaded agent, your rules, the draft and the approval from this screen and start again?')) return
    reset()
    navigate('/agent')
  }

  return (
    <div className="studio-dark">
      <div className="mx-auto max-w-7xl p-4">
        <header className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-slate-200 pb-3">
          <Link to="/" className="font-display whitespace-nowrap text-xl font-bold text-slate-900" title="Back to the home page">
            YOG<span className="text-glow"> Studio</span>
          </Link>
          <Stepper />
          <div className="ml-auto flex items-center gap-4 text-sm">
            <MotionToggle />
            <NavLink to="/studio" end className="text-slate-600 hover:text-slate-900" title="Back to the list of Studio tools" data-testid="all-tools">
              All tools
            </NavLink>
            <NavLink to="/check" className={({ isActive }) => (isActive ? 'font-semibold text-link' : 'text-slate-600 hover:text-slate-900')} title="Try a policy against one action, without uploading anything">
              Sandbox
            </NavLink>
            <button type="button" onClick={startOver} className="text-slate-600 hover:text-red-700" data-testid="start-over">
              Start over
            </button>
          </div>
        </header>
        <StatusBar />
        <ErrorBoundary>
          {/* each page eases in; keyed on the path so every navigation replays it */}
          <motion.div
            key={pathname}
            data-testid="page-transition"
            initial={reduce ? false : { opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.28, ease: 'easeOut' }}
          >
            {outlet}
          </motion.div>
        </ErrorBoundary>
      </div>
    </div>
  )
}
