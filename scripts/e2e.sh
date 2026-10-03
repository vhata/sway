#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
if [[ ! -f src/sway/web.py && ! -d src/sway/web && -z "$(find tests/e2e -type f -name '*.py' -print -quit)" ]]; then
  echo "Browser implementation pending; browser gate starts when web code or browser tests exist."
  exit 0
fi
# pytest-playwright clears its output directory at startup. Give every invocation
# fresh paths so rerunning a failure cannot erase its traces or server state.
# Keep these outside the default test-results/ too: even non-browser pytest
# sessions load the plugin and erase that directory.
mkdir -p browser-evidence
SWAY_E2E_RUN_DIR="$(mktemp -d "$SWAY_ROOT/browser-evidence/run-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
export SWAY_E2E_ARTIFACT_DIR="$SWAY_E2E_RUN_DIR/hosted"
echo "Browser evidence: $SWAY_E2E_RUN_DIR"
git rev-parse HEAD > "$SWAY_E2E_RUN_DIR/commit.txt"
printf '%q ' "$@" > "$SWAY_E2E_RUN_DIR/arguments.txt"
printf '\n' >> "$SWAY_E2E_RUN_DIR/arguments.txt"
set +e
uv run --locked pytest tests/e2e --browser chromium --tracing retain-on-failure "$@" \
  --output "$SWAY_E2E_RUN_DIR/playwright" --basetemp "$SWAY_E2E_RUN_DIR/runtime" \
  2>&1 | tee "$SWAY_E2E_RUN_DIR/pytest.log"
SWAY_E2E_STATUS="$?"
set -e
printf '%s\n' "$SWAY_E2E_STATUS" > "$SWAY_E2E_RUN_DIR/exit-status.txt"
exit "$SWAY_E2E_STATUS"
