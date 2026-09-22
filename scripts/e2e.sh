#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
exec uv run --locked pytest tests/e2e --browser chromium --tracing retain-on-failure "$@"
