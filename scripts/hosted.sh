#!/usr/bin/env bash
# Run one application process behind a TLS reverse proxy preserving Host.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
if [[ $# -ne 0 ]]; then
  echo "Configure SWAY_HOSTED_*; this launcher does not accept uvicorn overrides." >&2
  exit 2
fi
umask 077
exec uv run --locked uvicorn sway.hosting.web:create_app --factory \
  --host 127.0.0.1 --port "${SWAY_HOSTED_PORT:-8000}" --workers 1 \
  --no-proxy-headers --no-access-log
