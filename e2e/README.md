# Browser walkthrough (Playwright)

Not part of the pytest suite. With backend (:8000) and frontend (:5173) running:

```
cd e2e
npm init -y && npm install playwright && npx playwright install chromium
node ui.mjs
```
It walks Upload -> Rules -> Review (evaluate, approve) -> Patch -> Device (3am block) -> Check and prints PASS/FAIL per step.
It approves a policy, so it writes into `backend/data/policies/`. Needs the default fake LLM provider.
