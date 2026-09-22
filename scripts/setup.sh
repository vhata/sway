#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
uv sync --locked "$@"
scripts/install-tools.sh
git config core.hooksPath .githooks
