import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { open, readFile, rename } from "node:fs/promises";
import path from "node:path";
import { getPlatformProxy } from "wrangler";

// No deployment or implicit target: use a reviewed client configuration and account.
const [command, configPath, input, output] = process.argv.slice(2);
assert.ok(["capture", "restore", "undo"].includes(command));
assert.ok(configPath && input, "Expected command client.json checkpoint.json [receipt.json]");
const config = JSON.parse(await readFile(configPath, "utf8"));
assert.match(config.account_id ?? "", /^[a-f0-9]{32}$/);
assert.equal(config.account_id, process.env.CLOUDFLARE_ACCOUNT_ID);
assert.equal(config.services?.length, 1);
assert.equal(config.services[0].binding, "INSTALLATION");
assert.equal(config.services[0].remote, true);
assert.equal(config.services[0].service, process.env.SWAY_RECOVERY_TARGET);
assert.ok(!config.services[0].environment, "Use the exact deployed Worker name");
const target = { account: config.account_id, worker: config.services[0].service };
const snapshot = (value) => JSON.parse(JSON.stringify(value));
async function read(file) {
  return JSON.parse(await readFile(file, "utf8"));
}
async function save(file, data) {
  const temporary = `${file}.${randomBytes(8).toString("hex")}.tmp`;
  const handle = await open(temporary, "wx", 0o600);
  try {
    await handle.writeFile(`${JSON.stringify(data, null, 2)}\n`);
    await handle.sync();
  } finally {
    await handle.close();
  }
  await rename(temporary, file);
  const directory = await open(path.dirname(path.resolve(file)), "r");
  try {
    await directory.sync();
  } finally {
    await directory.close();
  }
}
const proxy = await getPlatformProxy({ configPath, remoteBindings: true, persist: false });
const service = proxy.env.INSTALLATION;
try {
  const current = snapshot(await service.recovery("inspect"));
  assert.match(current.objectId, /^[a-f0-9]{64}$/);
  const bookmark = () => service.recovery("bookmark", current.objectId);
  if (command === "capture") {
    // Exclusive creation prevents accidental replacement of a historical checkpoint.
    const reserved = await open(input, "wx", 0o600);
    await reserved.close();
    await save(input, { target, state: current, bookmark: await bookmark() });
    console.log(`Maintenance checkpoint saved: ${input}`);
  } else {
    const saved = await read(input);
    assert.deepEqual(saved.target, target, "Checkpoint belongs to another account or Worker");
    const desired = command === "undo" ? saved.before : saved;
    assert.equal(desired.state.objectId, current.objectId, "Checkpoint belongs to another object");
    assert.match(desired.bookmark, /^[a-f0-9-]+$/);
    let receipt;
    const receiptPath = command === "undo" ? input : output;
    assert.ok(receiptPath, "Restore requires a separate receipt path for undo and resume");
    assert.notEqual(path.resolve(input), path.resolve(output ?? `${input}.unused`));
    if (command === "undo") {
      receipt = saved;
    } else {
      try {
        const reserved = await open(receiptPath, "wx", 0o600);
        await reserved.close();
        receipt = {
          target,
          desired,
          before: { state: current, bookmark: await bookmark() },
          phase: "prepared",
        };
        // The original state is durable before any potentially destructive RPC.
        await save(receiptPath, receipt);
      } catch (error) {
        if (error.code !== "EEXIST") throw error;
        receipt = await read(receiptPath);
        assert.deepEqual(receipt.target, target);
        assert.deepEqual(receipt.desired, desired, "Receipt belongs to another restore");
      }
    }
    assert.equal(receipt.before.state.objectId, current.objectId);
    receipt.phase = command === "undo" ? "undo-prepared" : "restore-prepared";
    await save(receiptPath, receipt);
    receipt.returnedUndoBookmark = await service.recovery(
      "restore",
      current.objectId,
      desired.bookmark,
    );
    receipt.phase = command === "undo" ? "undo-scheduled" : "restore-scheduled";
    await save(receiptPath, receipt);
    try {
      await service.recovery("restart", current.objectId);
    } catch {
      // abort rejects RPC; only the subsequent state comparison proves recovery.
    }
    let restored;
    let failure;
    for (let attempt = 0; attempt < 20; attempt++) {
      try {
        restored = snapshot(await service.recovery("inspect"));
        break;
      } catch (error) {
        failure = error;
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
    }
    if (!restored) throw failure;
    assert.deepEqual(
      restored,
      desired.state,
      "Recovered SQL state differs; keep maintenance enabled",
    );
    receipt.phase = command === "undo" ? "undo-verified" : "restore-verified";
    await save(receiptPath, receipt);
    console.log(`Exact SQL state verified; maintenance remains enabled. Receipt: ${receiptPath}`);
  }
} finally {
  await proxy.dispose();
}
