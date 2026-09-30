# Installation recovery runbook

`Installation.recovery` is a private service-binding RPC on the actual application
class. There is no HTTP administration route. It rejects every call until a
reviewed deployment sets `SWAY_RECOVERY_MAINTENANCE=true`. Both the edge and the
object then return HTTP 503; bot alarms defer themselves for one minute without
advancing games. Maintenance is deployment configuration, outside the restored
database, so recovery cannot accidentally reopen the site.

This procedure needs an authorized maintenance window. Deploying it and restoring
the pilot are separate operator actions; implementing or rehearsing the tool does
not establish that production has been recovered. Do not change the `Installation`
class, migration history, namespace binding, or stable object name `installation`.

## Prepare and capture

1. Preserve the current application commit, complete deployed Wrangler
   configuration (including origin, limits and asset bindings), account ID,
   Worker name and namespace ID. Prepare dependencies with
   `scripts/cloudflare.sh prepare`. Review the exact deployment configuration;
   add `SWAY_RECOVERY_MAINTENANCE` to its `vars`, with string value `true`.
   Deploy that reviewed configuration using the existing deployment procedure.
   Check that the public origin responds 503. Wait for the deployment to finish;
   do not use gradual deployments with mixed maintenance values.
2. Save a local client file, for example `.cache/installation-client.json`:

   ```json
   {
     "name": "sway-installation-operator",
     "account_id": "REPLACE_WITH_REVIEWED_ACCOUNT_ID",
     "compatibility_date": "2026-09-25",
     "services": [
       { "binding": "INSTALLATION", "service": "sway-private-tables", "remote": true }
     ]
   }
   ```

3. Select the same account and Worker explicitly, then capture a checkpoint:

   ```sh
   export CLOUDFLARE_ACCOUNT_ID=<reviewed-account-id>
   export SWAY_RECOVERY_TARGET=sway-private-tables
   scripts/cloudflare-installation.sh capture .cache/installation-client.json .cache/baseline.json
   ```

   Capture reports no private rows. Its mode-0600 checkpoint contains the exact
   account, Worker, object ID, current bookmark, table counts and a schema/SQL
   digest covering every application table, including future tables. Keep it
   outside the Worker and preserve it securely with the matching application
   version. This is a PITR reference, not an independent backup: Cloudflare keeps
   recoverable history for 30 days. Namespace deletion loses that history.

All traffic reaching the object before its maintenance deployment completes must
finish before capture. Object storage operations gate concurrent input, and
capture runs only after the new maintenance instance responds. While maintenance
is enabled, do not call other private writers or run overlapping operator clients.

## Restore, verify, undo, reopen

Use an earlier captured checkpoint from this exact installation and compatible
application schema. The tool intentionally does not accept arbitrary timestamps
or unverified cross-installation bookmarks.

```sh
scripts/cloudflare-installation.sh restore .cache/installation-client.json .cache/baseline.json .cache/restore-receipt.json
# To undo that restore while still in maintenance:
scripts/cloudflare-installation.sh undo .cache/installation-client.json .cache/restore-receipt.json
```

The controller checks account, Worker and object ID before writes. It saves the
current snapshot and undo bookmark with atomic rename, file flush, directory
flush and mode 0600 **before** asking Cloudflare to schedule a restore. It saves
the returned undo bookmark as additional evidence, restarts the object and
compares the complete SQL digest/counts. A restart RPC error alone proves nothing.
If interrupted, rerun the same restore command and receipt path; its original undo
point is retained. Repeat the same undo command to finish an interrupted undo.
An empty checkpoint/receipt left by interruption during initial creation has no
armed restore; preserve it for diagnosis and use a new output path.

A verified restore leaves maintenance enabled. Review table counts and the
restored point with affected players before reopening. Whole-database recovery
also resurrects historical sessions, invitation secrets and recovery credentials:
a credential revoked after the checkpoint can become valid again. Resolve that
incident risk before reopening; this tool does not promise credential revocation
survives rollback. Revert only the maintenance variable in the reviewed deployment
configuration, deploy, then verify login, game revision/receipt behaviour and bot
progress. Deferred bot alarms resume within a minute (or a later request schedules
pending work). If validation fails, keep/re-enter maintenance and use the saved undo.

SQL verification does not attest player-visible correctness, arbitrary future
binary/KV payloads, or code/schema compatibility. The current app stores its state
in SQL; the disposable drill separately verifies its synthetic KV marker. For a
schema-changing incident, recover using the compatible code version first.

## Rehearsal and evidence

The [disposable recovery drill](README.md) calls the **same Installation recovery
methods**, including exact object matching and the complete SQL snapshot, through
a private Worker with its own `RecoveryDrill` namespace. It verifies restoration
of identities, sessions, game state, idempotency receipts and undo. Its synthetic
writers remain private drill-only methods; they are absent from production.
Local checks verify the guards and RPC path; real PITR requires the remote drill.
Neither proves that production has completed an authorized recovery window.

Sources: [Cloudflare PITR and its 30-day history](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/),
[private service-binding RPC](https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/rpc/).
