import { NavLink, Route, Routes } from 'react-router-dom'
import CheckPage from './pages/CheckPage'

const links: [string, string][] = [['/', 'Check']]

export default function App() {
  return (
    <div className="mx-auto max-w-6xl p-4">
      <header className="mb-6 flex items-center gap-6 border-b border-slate-200 pb-3">
        <h1 className="text-xl font-bold text-indigo-700">YOG Studio</h1>
        <nav className="flex gap-4 text-sm">
          {links.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) => (isActive ? 'font-semibold text-indigo-700' : 'text-slate-600 hover:text-slate-900')}
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<CheckPage />} />
      </Routes>
    </div>
  )
}
