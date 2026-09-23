#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
if [[ ! -f src/sway/web.py && ! -d src/sway/web && -z "$(find tests/e2e -type f -name '*.py' -print -quit)" ]]; then
  echo "Browser implementation pending; browser gate starts when web code or browser tests exist."
  exit 0
fi
exec uv run --locked pytest tests/e2e --browser chromium --tracing retain-on-failure "$@"
