#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
if sway_foundation_only; then
  echo "No engine coverage yet (foundation); gate starts when application code or tests exist."
  exit 0
fi
uv run --locked pytest --ignore=tests/e2e --cov=sway.engine --cov-branch --cov-report=term-missing --cov-report=xml --cov-report=json:coverage.json "$@"
uv run --locked python scripts/check-coverage.py coverage.json
