#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
uv run --locked ruff format "${@:-.}"
scripts/biome.sh format --write --no-errors-on-unmatched "${@:-.}"
