#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
uv run --locked ruff check "${@:-.}"
scripts/biome.sh lint --no-errors-on-unmatched "${@:-.}"
