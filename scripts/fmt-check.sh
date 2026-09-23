#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
uv run --locked ruff format --check "${@:-.}"
scripts/biome.sh format --no-errors-on-unmatched "${@:-.}"
