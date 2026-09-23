#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
if sway_foundation_only; then
  echo "No application tests yet (foundation); gate starts when application code or tests exist."
  exit 0
fi
exec uv run --locked pytest --ignore=tests/e2e "$@"
