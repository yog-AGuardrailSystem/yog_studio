# Browser tests (Playwright, driving an installed Chrome)

Not part of pytest. Start the backend with the offline fake LLM and the frontend, then run:

```
cd backend  ; $env:LLM_PROVIDER="fake" ; uv run python -m uvicorn app.main:app --port 8000
cd frontend ; npm run dev
cd e2e      ; npm ci
node workbench.mjs   # the YOG workbench at /studio
node landing.mjs     # landing + how-it-works: live explorer, example cards, finished-product wording, overflow
node motion.mjs      # motion registry count (target 300), pause control, OS reduced motion
node axe.mjs         # axe contrast and structure on every main screen
node ui.mjs          # agent tools flow: upload, rules, review/approve, patch, device 3am block
```

`ui.mjs` approves a policy, so it writes into `backend/data/policies/`. Set `CHROME_PATH` if Chrome is not found.
CI (`.github/workflows/ci-cd.yml`, job `e2e`) runs all five on every PR.
