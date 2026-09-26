import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { open, readFile, rename } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { getPlatformProxy } from "wrangler";

const directory = path.dirname(fileURLToPath(import.meta.url));
const local = process.argv.includes("--local");
const runId = randomBytes(16).toString("hex");
const checkpoint = path.join(directory, `proof-${runId}.json`);
const configuration = JSON.parse(await readFile(path.join(directory, "client.json"), "utf8"));
if (!local) {
  assert.match(configuration.account_id ?? "", /^[a-f0-9]{32}$/);
  assert.equal(
    configuration.account_id,
    process.env.CLOUDFLARE_ACCOUNT_ID,
    "Prepared and explicitly selected Cloudflare accounts must match",
  );
}
const proxy = await getPlatformProxy({
  configPath: path.join(directory, local ? "client.local.json" : "client.json"),
  remoteBindings: !local,
  persist: false,
});
const service = proxy.env.RECOVERY;
const evidence = {
  runId,
  worker: configuration.services[0].service,
  accountId: local ? "local" : configuration.account_id,
  phase: "started",
};
async function save() {
  const temporary = `${checkpoint}.${randomBytes(8).toString("hex")}.tmp`;
  const file = await open(temporary, "wx", 0o600);
  try {
    await file.writeFile(`${JSON.stringify(evidence, null, 2)}\n`);
    await file.sync();
  } finally {
    await file.close();
  }
  await rename(temporary, checkpoint);
}
async function restartAndInspect(proof, token) {
  try {
    await service.restart(runId);
  } catch {
    // ctx.abort deliberately rejects the in-flight RPC. State inspection below
    // establishes whether restoration actually happened; the error alone cannot.
  }
  let error;
  for (let attempt = 0; attempt < 20; attempt++) {
    try {
      return await service.inspect(runId, proof, token);
    } catch (caught) {
      error = caught;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
  throw error;
}
try {
  const proof = await service.seed(runId);
  evidence.proof = proof;
  const baseline = await service.inspect(runId, proof);
  assert.equal(baseline.revision, 1);
  assert.equal(baseline.status, "active");
  assert.deepEqual(baseline.receipts, ["baseline"]);
  assert.equal(baseline.old_session_valid, true);
  assert.equal(baseline.new_session_valid, false);
  assert.equal(baseline.marker, "baseline");
  evidence.baseline = baseline;
  if (!local) evidence.bookmark = await service.bookmark(runId);
  await save();

  const newToken = await service.mutate(runId, proof);
  evidence.newToken = newToken;
  const changed = await service.inspect(runId, proof, newToken);
  assert.equal(changed.revision, 2);
  assert.equal(changed.status, "cancelled");
  assert.deepEqual(changed.receipts, ["baseline", "after-bookmark"]);
  assert.equal(changed.old_session_valid, false);
  assert.equal(changed.new_session_valid, true);
  assert.equal(changed.marker, "changed");
  assert.notEqual(changed.digest, baseline.digest);
  evidence.changed = changed;
  // Capture the undo target before arming any restore. A lost response or an
  // object restart during prepare_restore cannot strand the original state.
  if (!local) evidence.changedBookmark = await service.bookmark(runId);
  evidence.phase = "mutated";
  await save();
  if (local) {
    console.log(
      "Private local RPC: identity, game, receipts and revocation checks passed. PITR not attempted.",
    );
  } else {
    evidence.undoBookmark = await service.prepare_restore(runId, evidence.bookmark);
    evidence.phase = "restore-scheduled";
    await save();
    const restored = await restartAndInspect(proof, newToken);
    assert.deepEqual(restored, baseline);
    assert.equal(await service.replay(runId, proof), 1);
    assert.deepEqual(await service.inspect(runId, proof, newToken), baseline);
    evidence.restored = restored;
    evidence.phase = "restored";
    await save();
    await service.prepare_restore(runId, evidence.changedBookmark);
    const undone = await restartAndInspect(proof, newToken);
    assert.deepEqual(undone, changed);
    evidence.phase = "restore-and-undo-verified";
    await save();
    console.log(
      "Remote PITR: exact application state, KV, revisions, receipts, credential validity and undo verified.",
    );
  }
  console.log(`Synthetic credential checkpoint (mode 0600): ${checkpoint}`);
} finally {
  await proxy.dispose();
}
