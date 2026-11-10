#!/usr/bin/env bash
# Post-deploy smoke test. Waits until the live site reports the expected commit, then checks key pages.
#   scripts/smoke.sh <site-url> <expected-commit-sha> [timeout-seconds]
# Used by .github/workflows/ci-cd.yml; also runnable by hand:  scripts/smoke.sh https://yog-studio.onrender.com $(git rev-parse HEAD)
set -u
SITE="${1:?site url required}"; SITE="${SITE%/}"
SHA="${2:?expected commit sha required}"
TIMEOUT="${3:-1500}"   # free-tier Docker builds take ~5-8 min; cold start adds ~1 min
INTERVAL=15
start=$(date +%s)

echo "Waiting for $SITE to run commit ${SHA:0:7} (timeout ${TIMEOUT}s)..."
while :; do
  body=$(curl -fsS -m 20 "$SITE/api/version" 2>/dev/null || true)
  live=$(printf '%s' "$body" | sed -n 's/.*"commit"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
  if [ -n "$live" ] && { [ "$live" = "$SHA" ] || [ "${live:0:7}" = "${SHA:0:7}" ]; }; then
    echo "Live commit matches: ${live:0:7}"; break
  fi
  now=$(date +%s)
  if [ $((now - start)) -ge "$TIMEOUT" ]; then
    echo "::error::Timed out. Live commit is '${live:-unreachable}', expected ${SHA:0:7}. Check the deploy in the Render dashboard."
    exit 1
  fi
  echo "  live=${live:-unreachable}; retrying in ${INTERVAL}s"
  sleep "$INTERVAL"
done

fail=0
check() { # path, must-contain
  code=$(curl -s -m 30 -o /tmp/smoke_body -w '%{http_code}' "$SITE$1" || echo 000)
  if [ "$code" != "200" ]; then echo "::error::$1 returned $code"; fail=1; return; fi
  if [ -n "${2:-}" ] && ! grep -q "$2" /tmp/smoke_body; then echo "::error::$1 is missing '$2'"; fail=1; return; fi
  echo "ok  $1"
}
check /api/health '"ok"'
check / 'id="root"'
check /how-it-works 'id="root"'
check /studio 'id="root"'
check /studio/workbench 'id="root"'
exit $fail
