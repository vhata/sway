#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
SWAY_BIOME="$SWAY_ROOT/.cache/tools/biome-$(cat .biome-version)"
if [[ ! -x "$SWAY_BIOME" ]]; then
  echo "Biome is missing. Run scripts/install-tools.sh." >&2
  exit 1
fi
exec "$SWAY_BIOME" "$@"
