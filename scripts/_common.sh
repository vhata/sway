#!/usr/bin/env bash
# Shared setup; source this file from a script, not from a login shell.
set -euo pipefail
SWAY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SWAY_ROOT"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$SWAY_ROOT/.cache/uv}"
export PRE_COMMIT_HOME="${PRE_COMMIT_HOME:-$SWAY_ROOT/.cache/pre-commit}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$SWAY_ROOT/.cache/playwright}"
if ! command -v uv >/dev/null 2>&1; then
  echo "Install uv $(cat .uv-version) and put it on PATH; see README.md." >&2
  exit 1
fi
