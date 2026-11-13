import { Link, NavLink, Outlet } from 'react-router-dom'
import { GlowBackground } from '../components/motion/GlowBackground'
import { SiteFooter } from '../components/SiteFooter'
import { MotionToggle } from '../lib/motion'

const navCls = ({ isActive }: { isActive: boolean }) =>
  isActive ? 'font-semibold text-white' : 'text-slate-300 hover:text-white'

export default function MarketingLayout() {
  return (
    <div className="mkt min-h-screen">
      <GlowBackground />
      <header className="sticky top-0 z-20 border-b border-white/10 bg-slate-950/70 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-3 sm:px-5">
          <Link to="/" className="font-display mr-3 whitespace-nowrap text-lg font-bold tracking-tight text-white">
            YOG<span className="text-glow"> Studio</span>
          </Link>
          <nav className="flex items-center gap-2 whitespace-nowrap text-sm sm:gap-5">
            <NavLink to="/" end className={(s) => `hidden sm:inline ${navCls(s)}`}>
              Home
            </NavLink>
            <NavLink to="/how-it-works" className={navCls}>
              How it works
            </NavLink>
            <NavLink to="/download" className={(s) => `hidden sm:inline ${navCls(s)}`}>
              Download
            </NavLink>
            <MotionToggle />
            <Link to="/studio" className="btn-primary">
              Open Studio
            </Link>
          </nav>
        </div>
      </header>
      <Outlet />
      <SiteFooter />
    </div>
  )
}
