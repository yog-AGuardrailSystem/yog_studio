import { Outlet } from 'react-router-dom'
import { SiteFooter } from '../components/SiteFooter'

/** /studio: the same black and gold theme as the marketing pages, but no sticky header, because the hub draws its own top row. */
export default function HubLayout() {
  return (
    <div className="mkt min-h-screen">
      <Outlet />
      <SiteFooter />
    </div>
  )
}
