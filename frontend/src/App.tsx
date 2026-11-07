import { Navigate, Route, Routes } from 'react-router-dom'
import MarketingLayout from './layouts/MarketingLayout'
import StudioLayout from './layouts/StudioLayout'
import AnalyzePage from './pages/AnalyzePage'
import CheckPage from './pages/CheckPage'
import DevicePage from './pages/DevicePage'
import LandingPage from './pages/LandingPage'
import ModifyPage from './pages/ModifyPage'
import ReviewPage from './pages/ReviewPage'
import RulesPage from './pages/RulesPage'

export default function App() {
  return (
    <Routes>
      <Route element={<MarketingLayout />}>
        <Route path="/" element={<LandingPage />} />
      </Route>
      <Route element={<StudioLayout />}>
        <Route path="/studio" element={<AnalyzePage />} />
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
