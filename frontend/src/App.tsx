import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import MarketingLayout from './layouts/MarketingLayout'
import StudioLayout from './layouts/StudioLayout'
import AnalyzePage from './pages/AnalyzePage'
import CheckPage from './pages/CheckPage'
import DevicePage from './pages/DevicePage'


import ModifyPage from './pages/ModifyPage'
import ReviewPage from './pages/ReviewPage'
import RulesPage from './pages/RulesPage'
import WorkbenchPage from './pages/WorkbenchPage'

// Marketing pages carry three.js + motion: load them as separate chunks so Studio stays light.
const LandingPage = lazy(() => import('./pages/LandingPage'))
const HowItWorksPage = lazy(() => import('./pages/HowItWorksPage'))
const StudioHubPage = lazy(() => import('./pages/StudioHubPage'))

export default function App() {
  return (
    <Routes>
      <Route element={<MarketingLayout />}>
        <Route path="/" element={<Suspense fallback={<div className="min-h-screen" />}><LandingPage /></Suspense>} />
        <Route path="/how-it-works" element={<Suspense fallback={<div className="min-h-screen" />}><HowItWorksPage /></Suspense>} />
        <Route path="/studio" element={<Suspense fallback={<div className="min-h-screen" />}><StudioHubPage /></Suspense>} />
      </Route>
      <Route element={<StudioLayout />}>
        <Route path="/studio/workbench" element={<WorkbenchPage />} />
        <Route path="/agent" element={<AnalyzePage />} />
        <Route path="/rules" element={<RulesPage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/modify" element={<ModifyPage />} />
        <Route path="/device" element={<DevicePage />} />
        <Route path="/check" element={<CheckPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
