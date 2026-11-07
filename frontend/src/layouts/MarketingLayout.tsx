import { Link, NavLink, Outlet } from 'react-router-dom'

export default function MarketingLayout() {
  return (
    <div className="mkt min-h-screen bg-white text-slate-900">
      <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
          <Link to="/" className="font-display whitespace-nowrap text-lg font-bold tracking-tight">
            YOG<span className="text-brand"> Studio</span>
          </Link>
          <nav className="flex items-center gap-4 whitespace-nowrap text-sm sm:gap-5">
            <NavLink to="/" end className={({ isActive }) => (isActive ? 'hidden font-semibold sm:inline' : 'hidden text-slate-600 hover:text-slate-900 sm:inline')}>
              Home
            </NavLink>
            <NavLink to="/how-it-works" className={({ isActive }) => (isActive ? 'font-semibold' : 'text-slate-600 hover:text-slate-900')}>
              How it works
            </NavLink>
            <Link to="/studio" className="btn-primary">
              Open Studio
            </Link>
          </nav>
        </div>
      </header>
      <Outlet />
      <footer className="border-t border-slate-200 bg-slate-50">
        <div className="mx-auto grid max-w-6xl gap-6 px-5 py-10 text-sm text-slate-600 sm:grid-cols-3">
          <div>
            <p className="font-display font-bold text-slate-900">YOG Studio</p>
            <p className="mt-1">Final-year B.Tech CS project, M S Ramaiah University of Applied Sciences.</p>
          </div>
          <div>
            <p className="font-semibold text-slate-900">Team</p>
            {/* TODO(vasanthan): replace with the real names */}
            <p className="mt-1">Engine team: {'{{ENGINE TEAM NAMES}}'}</p>
            <p>Studio: {'{{STUDIO TEAM NAMES}}'}</p>
          </div>
          <div>
            <p className="font-semibold text-slate-900">Code</p>
            <p className="mt-1">
              <a className="link" href="https://github.com/yog-AGuardrailSystem" target="_blank" rel="noreferrer">
                github.com/yog-AGuardrailSystem
              </a>
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}
