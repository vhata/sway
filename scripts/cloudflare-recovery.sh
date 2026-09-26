#!/usr/bin/env bash
# Stage an isolated, RPC-only recovery worker; deploy/run are explicit operations.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"
mode="${1:-prepare}"
case "$mode" in prepare|deploy|dev|run|run-local) ;; *) echo "Use prepare, deploy, dev, run or run-local." >&2; exit 2 ;; esac
stage="$SWAY_ROOT/.cache/cloudflare-recovery"
if [[ "$mode" == deploy || "$mode" == run ]]; then
  : "${CLOUDFLARE_ACCOUNT_ID:?Export the reviewed Cloudflare account ID for remote operations}"
fi
if [[ "$mode" == prepare || "$mode" == deploy || "$mode" == dev ]]; then
  scripts/cloudflare.sh prepare
  uv run --locked --project deployment/cloudflare python - <<'PY'
import json
import os
import re
import shutil
from pathlib import Path
root = Path.cwd()
source = root / 'deployment/cloudflare'
stage = root / '.cache/cloudflare-recovery'
name = os.environ.get('SWAY_RECOVERY_WORKER', 'sway-recovery-drill')
if not re.fullmatch(r'sway-recovery-[a-z0-9][a-z0-9-]{0,45}', name):
    raise ValueError('SWAY_RECOVERY_WORKER must start with sway-recovery-')
stage.mkdir(parents=True, exist_ok=True)
for name_ in ('worker.py', 'controller.mjs'):
    shutil.copy2(source / 'recovery' / name_, stage / name_)
config = json.loads((source / 'recovery/wrangler.jsonc').read_text())
config['name'] = name
account = os.environ.get('CLOUDFLARE_ACCOUNT_ID')
if account:
    if not re.fullmatch(r'[a-f0-9]{32}', account):
        raise ValueError('Invalid CLOUDFLARE_ACCOUNT_ID')
    config['account_id'] = account
(stage / 'wrangler.jsonc').write_text(json.dumps(config, indent=2) + '\n')
for local in (False, True):
    client = {'name': name + '-client', 'compatibility_date': config['compatibility_date'],
              'services': [{'binding': 'RECOVERY', 'service': name, 'remote': not local}]}
    if account:
        client['account_id'] = account
    filename = 'client.local.json' if local else 'client.json'
    (stage / filename).write_text(json.dumps(client, indent=2) + '\n')
packages = stage / 'python_modules'
if packages.exists():
    shutil.rmtree(packages)
shutil.copytree(source / 'python_modules', packages)
shutil.copy2(source / 'src/entry.py', packages / 'recovery_runtime.py')
modules = stage / 'node_modules'
if not modules.exists():
    modules.symlink_to(source / 'node_modules', target_is_directory=True)
print(f'Prepared private recovery worker {name}; configuration: {stage / "wrangler.jsonc"}')
PY
fi
cd "$stage"
case "$mode" in
  prepare) exit 0 ;;
  deploy) exec node "$SWAY_ROOT/deployment/cloudflare/node_modules/wrangler/bin/wrangler.js" deploy --config "$stage/wrangler.jsonc" ;;
  dev) exec node "$SWAY_ROOT/deployment/cloudflare/node_modules/wrangler/bin/wrangler.js" dev --config "$stage/wrangler.jsonc" --local --port 8811 ;;
  run) exec node "$stage/controller.mjs" ;;
  run-local) exec node "$stage/controller.mjs" --local ;;
esac
