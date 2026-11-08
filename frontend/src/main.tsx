import { MotionConfig } from 'motion/react'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { AppStateProvider } from './state'

// reducedMotion="user": transform animations switch off for people who set "reduce motion" in their OS.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <AppStateProvider>
          <App />
        </AppStateProvider>
      </BrowserRouter>
    </MotionConfig>
  </StrictMode>,
)
