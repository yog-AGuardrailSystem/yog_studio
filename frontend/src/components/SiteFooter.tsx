/** The footer shared by the marketing pages and the Studio hub. */
export function SiteFooter() {
  return (
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
          <p className="mt-1"><a className="link" href="/download">Download yogc for Windows or Linux</a></p>
        </div>
      </div>
    </footer>
  )
}
