# Private Cloudflare recovery drill

This operator tool deploys a separate RPC-only Worker and a separate SQLite
Durable Object namespace. It reuses Sway's actual hosted runtime and domain
services. It never binds to the application's `Installation` namespace, and
exposes no HTTP handler, `workers.dev` URL, preview URL or custom route.

Use a fresh name beginning with `sway-recovery-`; the default is
`sway-recovery-drill`. Preparing files and checking local RPC do not deploy.

```sh
export SWAY_RECOVERY_WORKER=sway-recovery-drill
scripts/cloudflare-recovery.sh prepare
# Inspect .cache/cloudflare-recovery/wrangler.jsonc and confirm the account.
```

For a local check, run `scripts/cloudflare-recovery.sh dev` in one terminal and
`scripts/cloudflare-recovery.sh run-local` in another. The latter uses a private
local service binding and asserts real identity, game, receipt and credential
rotation behaviour. PITR is unavailable locally and is explicitly not attempted.
Stop the local development process afterward.

After authenticating Wrangler and reviewing the account/name, the explicit
remote operations are:

```sh
export CLOUDFLARE_ACCOUNT_ID=<reviewed-account-id>
scripts/cloudflare-recovery.sh deploy
scripts/cloudflare-recovery.sh run
```

`deploy` stages the pinned application dependencies and publishes only the
isolated harness. `run` uses Wrangler's `getPlatformProxy` with a remote service
binding; the controller runs locally and the synthetic database runs on
Cloudflare. Do not add `remote: true` to a Durable Object binding: this gateway
through a service binding is the supported approach.

Each run uses a fresh random object name. It creates two synthetic identities,
a human-only game, and one accepted command/receipt. After recording a bookmark,
it commits another command, rotates the host recovery credential (revoking the
old session), and cancels the game. The controller then restores and verifies:

- Exact application table digest and SQL revision/status.
- The original receipt remains; the later receipt disappears.
- Replaying the original request does not advance state.
- Historical session validity and the KV marker return to their original values.
- Undo restores the changed database and changed credential validity exactly.

The controller captures a bookmark for the changed state before scheduling any
restore. The effective account ID and worker name are recorded with the evidence. Remote
commands require an explicit account ID matching the prepared configuration.
Baseline, changed-state and returned undo bookmarks are saved outside
the Durable Object. Checkpoints are written atomically, flushed, mode `0600`, in
`.cache/cloudflare-recovery/proof-*.json`. They contain synthetic credentials;
do not publish or commit them. Output prints only the result and checkpoint path.
An interrupted run retains its latest checkpoint; do not assume an interrupted
restore succeeded merely because the abort RPC failed. After the changed-state
bookmark has been saved, resume against the same prepared account/Worker:

```sh
scripts/cloudflare-recovery.sh run --resume /absolute/path/to/proof-<run-id>.json
```

Resume checks the checkpoint target, skips creation/mutation, then repeats the
baseline restore and changed-state undo. Completed checkpoints cannot be resumed.
Remote RPC results are normalized to JSON data before comparison because gateway
proxy identity is unrelated to the stored application state.

Whole-database recovery also restores old credential validity. This drill tests
that historical behaviour deliberately; it does not claim revoked credentials
remain revoked after restoring an older database. It is not a production recovery
endpoint or an account migration tool.

After preserving sanitized evidence, retire only the isolated recovery Worker
and its `RecoveryDrill` namespace using Cloudflare's class deletion procedure.
Do not delete or modify the application's `Installation` class. There is no
automatic cleanup command because namespace deletion permanently removes its
recovery history.

Sources: [PITR API](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/),
[private service bindings](https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/rpc/),
[remote binding gateway](https://developers.cloudflare.com/workers/local-development/),
[class deletion](https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/).
