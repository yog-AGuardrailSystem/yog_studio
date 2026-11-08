# Deploy to Render (free tier)

One Docker web service serves the UI at `/` and the API at `/api` (see `Dockerfile`, `render.yaml`, `backend/app/asgi.py`).

1. Merge/push this branch to GitHub (`feature/render-deploy` -> `main` via PR).
2. render.com -> New + -> **Blueprint** -> connect the GitHub repo -> it reads `render.yaml` -> Apply. (Or New + -> Web Service -> Docker, plan Free, health check path `/api/health`.)
3. First build takes ~5-8 min. Your URL is `https://yog-studio.onrender.com` (name may differ).
4. Optional real LLM: Render dashboard -> Environment -> `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...`.

## Free-tier facts to plan around
- Sleeps after ~15 min idle; first request then takes ~30-60 s. **Open the URL a few minutes before the demo** and click around.
- Disk is wiped on every restart/deploy: approved policies vanish. Re-do Rules -> "Use prepared demo policy" -> Run scenarios -> Approve before showing the Device page.
- The service is public and has no login: anyone with the link can approve policies and drive the simulated device (state is shared by everyone). Fine for a demo, do not put secrets in it, and share the link only with friends.
- 512 MB RAM is plenty for the offline fake LLM.

## CI/CD: merging to `main` deploys automatically
Workflow: `.github/workflows/ci-cd.yml`.

| When | What runs |
|---|---|
| Every pull request, and every push to `main` | **Test**: frontend `npm ci`, build (type-check), lint, `npm run test:mirror`; backend `pytest`. |
| Push to `main` (a merged PR) **and** Test passed | **Deploy**: calls the Render deploy hook for that exact commit, then `scripts/smoke.sh` waits until `https://<site>/api/version` reports that commit and checks `/api/health`, `/`, `/how-it-works`, `/studio`. The run fails if the new version never comes up (~25 min limit). |

A failing test blocks the deploy. A deploy that never goes live shows as a red run in GitHub (Actions tab).

### One-time setup (two minutes, needs your Render and GitHub accounts)
1. **Render deploy hook:** Render dashboard -> `yog-studio` -> **Settings** -> **Deploy Hook** -> copy the URL (looks like `https://api.render.com/deploy/srv-...?key=...`). Treat it like a password.
2. **GitHub secret:** repo -> **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret** -> name `RENDER_DEPLOY_HOOK`, value = the URL.
3. **Stop Render deploying on its own** (otherwise every merge deploys twice, once before the tests finish): Render -> `yog-studio` -> **Settings** -> **Build & Deploy** -> **Auto-Deploy** -> **Off**.
4. Optional: if your site URL differs from `https://yog-studio.onrender.com`, add a repo **variable** (same page, "Variables" tab) named `SITE_URL`.

Until step 2 is done, the Deploy job prints a warning and skips (it does not fail), so merging is still safe.

### Run it by hand
- Trigger a deploy without a merge: GitHub -> Actions -> CI/CD -> **Run workflow** (on `main`).
- Check a live site: `scripts/smoke.sh https://yog-studio.onrender.com $(git rev-parse HEAD)`.
- `/api/version` returns `{"commit": "<sha>"}` (Render provides `RENDER_GIT_COMMIT`); locally it is `unknown`.
