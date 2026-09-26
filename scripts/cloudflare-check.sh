#!/usr/bin/env bash
# Run shared contracts on native SQLite and real local workerd; never deploy.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
scripts/cloudflare.sh prepare
cp deployment/cloudflare/src/entry.py deployment/cloudflare/python_modules/cloudflare_runtime.py
cp deployment/cloudflare/contract_checks.py deployment/cloudflare/python_modules/contract_checks.py
trap 'rm -f "$SWAY_ROOT/deployment/cloudflare/python_modules/cloudflare_runtime.py" "$SWAY_ROOT/deployment/cloudflare/python_modules/contract_checks.py"' EXIT
uv run --locked pytest -q tests/test_cloudflare_contract.py
uv run --locked python scripts/cloudflare-check.py "$@"
