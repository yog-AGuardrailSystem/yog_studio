import { NavLink, Outlet } from 'react-router-dom'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { StatusBar } from '../components/StatusBar'

const links: [string, string][] = [
  ['/studio', 'Upload & Tools'],
  ['/rules', 'Rules'],
  ['/review', 'Review'],
  ['/modify', 'Patch'],
  ['/device', 'Device'],
  ['/check', 'Check'],
]

export default function StudioLayout() {
  return (
    <div className="mx-auto max-w-6xl p-4">
      <header className="mb-4 flex flex-wrap items-center gap-6 border-b border-slate-200 pb-3">
        <NavLink to="/" className="text-xl font-bold text-indigo-700" title="Back to the home page">
          YOG Studio
        </NavLink>
        <nav className="flex gap-4 text-sm">
          {links.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => (isActive ? 'font-semibold text-indigo-700' : 'text-slate-600 hover:text-slate-900')}
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <StatusBar />
      <ErrorBoundary>
        <Outlet />
      </ErrorBoundary>
    </div>
  )
}
