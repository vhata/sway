#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
if [[ ! -f src/sway/web.py && ! -d src/sway/web ]]; then
  echo "Web implementation pending; installed-wheel web smoke check is not applicable yet."
  exit 0
fi
SWAY_WHEEL="${1:-}"
if [[ -z "$SWAY_WHEEL" ]]; then
  SWAY_WHEEL="$(uv run --locked python - <<'PYCODE'
from pathlib import Path
import tomllib
with Path("pyproject.toml").open("rb") as source:
    project = tomllib.load(source)["project"]
name = project["name"].replace("-", "_")
version = project["version"]
paths = list(Path("dist").glob(f"{name}-{version}-*.whl"))
if len(paths) != 1:
    raise SystemExit("Build exactly one wheel for the current project version first.")
print(paths[0].resolve())
PYCODE
)"
else
  SWAY_WHEEL="$(cd "$(dirname "$SWAY_WHEEL")" && pwd)/$(basename "$SWAY_WHEEL")"
fi
SWAY_SMOKE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/sway-wheel.XXXXXX")"
trap 'rm -rf "$SWAY_SMOKE_ROOT"' EXIT
uv export --locked --no-dev --no-emit-project --format requirements-txt   --output-file "$SWAY_SMOKE_ROOT/runtime.txt" >/dev/null
uv venv --python "$SWAY_ROOT/.venv/bin/python" "$SWAY_SMOKE_ROOT/venv"
uv pip sync --python "$SWAY_SMOKE_ROOT/venv/bin/python" --require-hashes "$SWAY_SMOKE_ROOT/runtime.txt"
uv pip install --python "$SWAY_SMOKE_ROOT/venv/bin/python" --no-deps "$SWAY_WHEEL"
cp "$SWAY_ROOT/scripts/check-installed.py" "$SWAY_SMOKE_ROOT/check-installed.py"
cd "$SWAY_SMOKE_ROOT"
env -u PYTHONPATH -u VIRTUAL_ENV uv run --no-project --no-sync   --python "$SWAY_SMOKE_ROOT/venv/bin/python" python -I check-installed.py
