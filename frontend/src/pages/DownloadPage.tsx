import { useEffect, useState } from 'react'
import { listDownloads, type DownloadFile, type DownloadManifest } from '../api/downloads'

const ENGINE_REPO = 'https://github.com/yog-AGuardrailSystem/yog_engine'
const BUILD = 'cc -std=c11 -O2 -I src -I include src/lexer/lexer.c src/parser/*.c src/sema/*.c src/ir/*.c src/vm/*.c src/api/yog.c tools/yogc.c -o yogc'

const kb = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`)

function Code({ children }: { children: string }) {
  return <pre className="mt-2 overflow-x-auto rounded-lg border border-white/10 bg-black/50 p-3 font-mono text-xs leading-6 text-slate-200" style={{ fontVariantLigatures: 'none' }}>{children}</pre>
}

function FileButton({ f, primary }: { f: DownloadFile | undefined; primary?: boolean }) {
  if (!f) return null
  return (
    <a href={f.url} download className={primary ? 'btn-primary btn-lg' : 'btn-secondary'} data-testid={`dl-${f.kind}`}>
      {f.kind === 'installer' ? 'Download the installer' : f.kind === 'zip' ? 'Zip, no installer' : 'Download for Linux'}
      <span className="ml-2 text-xs opacity-75">{kb(f.size)}</span>
    </a>
  )
}

export default function DownloadPage() {
  const [m, setM] = useState<DownloadManifest | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => { listDownloads().then(setM).catch(() => setError(true)) }, [])
  const by = (kind: string) => m?.files.find((f) => f.kind === kind)

  return (
    <main className="mx-auto max-w-6xl px-5 pb-20 pt-14" data-testid="download-page">
      <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-glow">Download</p>
      <h1 className="font-display max-w-3xl text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">Get yogc, the YOG compiler.</h1>
      <p className="mt-4 max-w-2xl text-lg text-slate-300">
        The same C compiler Studio uses to make its decisions, as a command-line tool for your own machine.
        {m?.engine_commit && <> Built from yog_engine commit <code>{m.engine_commit}</code>.</>}
      </p>

      {error && <p className="mt-6 rounded border border-amber-600 bg-amber-950/40 p-3 text-amber-200" role="alert">The download list could not be loaded. Try again in a moment.</p>}
      {m && !m.available && (
        <p className="mt-6 rounded border border-amber-600 bg-amber-950/40 p-3 text-sm text-amber-200" role="status" data-testid="dl-unavailable">
          No packages on this server. {m.note}
        </p>
      )}

      <div className="mt-10 grid gap-5 md:grid-cols-2">
        <section className="glass min-w-0 p-6" aria-labelledby="dl-win">
          <h2 id="dl-win" className="font-display text-2xl font-bold">Windows</h2>
          <p className="mt-1 text-sm text-slate-300">64-bit, Windows 10 or later. Installs for your account only (no administrator rights), adds <code>yogc</code> to your PATH, and can be removed from Installed apps.</p>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <FileButton f={by('installer')} primary />
            <FileButton f={by('zip')} />
          </div>
          <p className="mt-4 text-sm text-slate-400">Then open a new terminal:</p>
          <Code>{'cd %LOCALAPPDATA%\\Programs\\YOG\\examples\nyogc check policy.yog alice can_delete database_1'}</Code>
        </section>

        <section className="glass min-w-0 p-6" aria-labelledby="dl-linux">
          <h2 id="dl-linux" className="font-display text-2xl font-bold">Linux</h2>
          <p className="mt-1 text-sm text-slate-300">x86-64, statically linked, so it runs on any distribution (and under WSL on Windows).</p>
          <div className="mt-4 flex flex-wrap items-center gap-3"><FileButton f={by('tarball')} primary /></div>
          <p className="mt-4 text-sm text-slate-400">Unpack and install to <code>~/.local/bin</code>:</p>
          <Code>{'tar -xzf yog-linux-x64.tar.gz\n./yog-linux-x64/install.sh'}</Code>
        </section>
      </div>

      <section className="mt-5 rounded-xl border border-amber-500/40 bg-amber-950/20 p-5 text-sm text-amber-100" aria-labelledby="dl-unsigned" data-testid="dl-unsigned-note">
        <h2 id="dl-unsigned" className="font-semibold">The Windows files are not code-signed</h2>
        <p className="mt-1">Windows SmartScreen will say the publisher is unknown: choose <b>More info</b>, then <b>Run anyway</b>. On PCs where <b>Smart App Control</b> is turned on, Windows blocks unsigned programs completely; use the Linux build under WSL, or build from source below. Check the SHA-256 of what you downloaded against the table at the bottom.</p>
      </section>

      <section className="mt-12" aria-labelledby="dl-use">
        <h2 id="dl-use" className="font-display text-2xl font-bold">Using it</h2>
        <div className="mt-4 grid gap-5 md:grid-cols-2">
          <div className="min-w-0">
            <p className="text-sm text-slate-300">Decide one request (the packages include this <code>policy.yog</code>):</p>
            <Code>{'yogc check policy.yog alice can_delete database_1\nALLOW|allow clause at line 10 matched\n\nyogc check policy.yog bob can_delete database_1 --trace\nDENY|deny clause at line 13 matched'}</Code>
          </div>
          <div className="min-w-0">
            <p className="text-sm text-slate-300">Other commands:</p>
            <Code>{'yogc batch policy.yog      # one request per line on stdin\nyogc run   policy.yog      # run every query in the file\nyogc ir    policy.yog      # print the compiled clause table'}</Code>
            <p className="mt-2 text-sm text-slate-400">Exit status: 0 allowed, 3 denied, 1 the policy does not compile, 2 usage or file error. DENY beats ALLOW, anything not allowed is denied, and an error never gives ALLOW.</p>
          </div>
        </div>
        <p className="mt-4 max-w-3xl text-sm text-slate-400">Context facts passed with <code>--context</code> are split at every <code>;</code>, even inside quotes, so pass only context your own program builds, never raw text from users or a model.</p>
      </section>

      <section className="mt-12" aria-labelledby="dl-src">
        <h2 id="dl-src" className="font-display text-2xl font-bold">macOS and everything else: build from source</h2>
        <p className="mt-2 max-w-3xl text-sm text-slate-300">Any C11 compiler works. In the <code>yog</code> folder of <a className="link" href={ENGINE_REPO} target="_blank" rel="noreferrer">yog_engine</a>:</p>
        <Code>{BUILD}</Code>
      </section>

      {m?.available && (
        <section className="mt-12" aria-labelledby="dl-sums">
          <h2 id="dl-sums" className="font-display text-2xl font-bold">Checksums</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="dl-checksums">
              <thead className="text-slate-400"><tr><th className="py-1 pr-4 font-medium">File</th><th className="py-1 pr-4 font-medium">Size</th><th className="py-1 font-medium">SHA-256</th></tr></thead>
              <tbody>
                {m.files.map((f) => (
                  <tr key={f.name} className="border-t border-white/10">
                    <td className="py-2 pr-4 font-mono text-xs">{f.name}</td>
                    <td className="py-2 pr-4 text-slate-300">{kb(f.size)}</td>
                    <td className="py-2 break-all font-mono text-xs text-slate-300">{f.sha256}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-sm text-slate-400">Windows: <code>Get-FileHash .\yog-setup-windows-x64.exe</code> · Linux: <code>sha256sum yog-linux-x64.tar.gz</code>{m.checksums_url && <> · <a className="link" href={m.checksums_url}>SHA256SUMS.txt</a></>}</p>
        </section>
      )}

      <p className="mt-12 max-w-3xl text-sm text-slate-400">
        yogc is written by the YOG engine team and released under the MIT license (included in every package). Studio builds these packages from the exact engine version it runs.
      </p>
    </main>
  )
}
