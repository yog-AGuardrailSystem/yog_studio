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
