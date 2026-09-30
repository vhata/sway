#!/usr/bin/env bash
# Private operator RPC client. Never deploys or changes maintenance configuration.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
: "${CLOUDFLARE_ACCOUNT_ID:?Export the reviewed Cloudflare account ID}"
: "${SWAY_RECOVERY_TARGET:?Export the exact reviewed Worker name}"
exec node deployment/cloudflare/recovery/installation.mjs "$@"
