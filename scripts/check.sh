#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
scripts/fmt-check.sh
scripts/lint.sh
scripts/typecheck.sh
scripts/coverage.sh "$@"
scripts/build.sh
scripts/install-smoke.sh
