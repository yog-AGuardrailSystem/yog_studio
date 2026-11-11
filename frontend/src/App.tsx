import { lazy, Suspense, type ComponentType, type LazyExoticComponent } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Skeleton } from './components/Skeleton'
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

// Each Studio tool is its own chunk: opening the workbench never downloads the Red-Team page.
const WhyPage = lazy(() => import('./pages/tools/WhyPage'))
const MapPage = lazy(() => import('./pages/tools/MapPage'))
const GapsPage = lazy(() => import('./pages/tools/GapsPage'))
const RedTeamPage = lazy(() => import('./pages/tools/RedTeamPage'))
const StrengthPage = lazy(() => import('./pages/tools/StrengthPage'))
const TemplatesPage = lazy(() => import('./pages/tools/TemplatesPage'))
const HistoryPage = lazy(() => import('./pages/tools/HistoryPage'))
const AuditPage = lazy(() => import('./pages/tools/AuditPage'))
const ReplayPage = lazy(() => import('./pages/tools/ReplayPage'))
const SdkPage = lazy(() => import('./pages/tools/SdkPage'))
const ExportPage = lazy(() => import('./pages/tools/ExportPage'))
const ScorecardPage = lazy(() => import('./pages/tools/ScorecardPage'))

const fallback = (
  <div className="space-y-3" role="status" aria-label="Loading">
    <Skeleton className="h-10 w-1/2" />
    <Skeleton className="h-40 w-full" />
  </div>
)
const tool = (C: LazyExoticComponent<ComponentType>) => <Suspense fallback={fallback}><C /></Suspense>

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
        <Route path="/studio/why" element={tool(WhyPage)} />
        <Route path="/studio/map" element={tool(MapPage)} />
        <Route path="/studio/gaps" element={tool(GapsPage)} />
        <Route path="/studio/red-team" element={tool(RedTeamPage)} />
        <Route path="/studio/strength" element={tool(StrengthPage)} />
        <Route path="/studio/templates" element={tool(TemplatesPage)} />
        <Route path="/studio/history" element={tool(HistoryPage)} />
        <Route path="/studio/audit" element={tool(AuditPage)} />
        <Route path="/studio/replay" element={tool(ReplayPage)} />
        <Route path="/studio/sdk" element={tool(SdkPage)} />
        <Route path="/studio/export" element={tool(ExportPage)} />
        <Route path="/studio/scorecard" element={tool(ScorecardPage)} />
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
