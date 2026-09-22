#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
export SWAY_DATA_DIR="${SWAY_DATA_DIR:-$SWAY_ROOT/.runtime}"
exec uv run --locked uvicorn "${SWAY_APP:-sway.web:app}" --host 127.0.0.1 --reload "$@"
