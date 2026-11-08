import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { MotionProvider } from './lib/motion'
import { AppStateProvider } from './state'

// MotionProvider: transform animations switch off for the OS "reduce motion" setting or the in-app pause button.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MotionProvider>
      <BrowserRouter>
        <AppStateProvider>
          <App />
        </AppStateProvider>
      </BrowserRouter>
    </MotionProvider>
  </StrictMode>,
)
