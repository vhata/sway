#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
exec uv run --locked pytest --ignore=tests/e2e --cov=sway.engine --cov-branch --cov-report=term-missing --cov-report=xml "$@"
