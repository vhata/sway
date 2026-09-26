#!/usr/bin/env bash
# Build a separate Workers dependency environment, then invoke the pinned CLI.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
cd deployment/cloudflare
# Test support is never included in a production build.
rm -f python_modules/cloudflare_runtime.py python_modules/contract_checks.py
npm ci --no-audit --no-fund
uv run --locked pywrangler sync
uv run --locked python - <<'PY'
import shutil
from pathlib import Path
source = Path('../../src/sway')
target = Path('python_modules/sway')
if target.exists():
    shutil.rmtree(target)
shutil.copytree(source, target, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
assets = Path('public/static')
if assets.exists():
    shutil.rmtree(assets)
shutil.copytree(source / 'static', assets)
PY
if [[ "${1:-}" == prepare ]]; then
  exit 0
fi
if [[ $# -eq 0 ]]; then
  set -- dev --local --port 8799 --local-protocol https
fi
exec uv run --locked pywrangler "$@"
