#!/usr/bin/env bash
# Exercise the isolated recovery drill locally; never deploy or attempt PITR.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
exec uv run --locked python scripts/cloudflare-recovery-check.py "$@"
