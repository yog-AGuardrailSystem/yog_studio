import { Link, NavLink, Outlet } from 'react-router-dom'
import { GlowBackground } from '../components/motion/GlowBackground'

const navCls = ({ isActive }: { isActive: boolean }) =>
  isActive ? 'font-semibold text-white' : 'text-slate-300 hover:text-white'

export default function MarketingLayout() {
  return (
    <div className="mkt min-h-screen">
      <GlowBackground />
      <header className="sticky top-0 z-20 border-b border-white/10 bg-slate-950/70 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
          <Link to="/" className="font-display whitespace-nowrap text-lg font-bold tracking-tight text-white">
            YOG<span className="text-glow"> Studio</span>
          </Link>
          <nav className="flex items-center gap-4 whitespace-nowrap text-sm sm:gap-5">
            <NavLink to="/" end className={(s) => `hidden sm:inline ${navCls(s)}`}>
              Home
            </NavLink>
            <NavLink to="/how-it-works" className={navCls}>
              How it works
            </NavLink>
            <Link to="/studio" className="btn-primary">
              Open Studio
            </Link>
          </nav>
        </div>
      </header>
      <Outlet />
      <footer className="border-t border-white/10 bg-black/30">
        <div className="mx-auto grid max-w-6xl gap-6 px-5 py-10 text-sm text-slate-400 sm:grid-cols-3">
          <div>
            <p className="font-display font-bold text-white">YOG Studio</p>
            <p className="mt-1">Final-year B.Tech CS project, M S Ramaiah University of Applied Sciences.</p>
          </div>
          <div>
            <p className="font-semibold text-white">Team</p>
            <p className="mt-1">The YOG engine team and the Studio team.</p>
          </div>
          <div>
            <p className="font-semibold text-white">Code</p>
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
