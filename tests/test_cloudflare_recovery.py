"""Exercise private recovery boundaries without emulating Cloudflare PITR itself."""

import asyncio
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest

ENTRY = Path(__file__).parents[1] / "deployment/cloudflare/src/entry.py"


def entry(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    def response(text: str, status: int, headers: dict[str, str]) -> tuple[object, ...]:
        return text, status, headers

    workers = SimpleNamespace(
        DurableObject=object,
        WorkerEntrypoint=object,
        Response=response,
        asgi=SimpleNamespace(),
    )
    monkeypatch.setitem(sys.modules, "workers", cast(Any, workers))
    return runpy.run_path(str(ENTRY))


def instance(namespace: dict[str, Any], *, maintenance: bool) -> Any:
    obj = namespace["Installation"].__new__(namespace["Installation"])
    obj.env = SimpleNamespace(SWAY_RECOVERY_MAINTENANCE=str(maintenance).lower())
    obj.ctx = SimpleNamespace(
        id="a" * 64,
        storage=SimpleNamespace(
            sync=AsyncMock(),
            getCurrentBookmark=AsyncMock(return_value="bookmark"),
            onNextSessionRestoreBookmark=AsyncMock(return_value="undo"),
            setAlarm=AsyncMock(),
        ),
        abort=Mock(side_effect=RuntimeError("aborted")),
    )
    obj.runtime = SimpleNamespace(service=SimpleNamespace(pending_bot_games=Mock()))
    return obj


def test_recovery_requires_maintenance_and_exact_object(monkeypatch: pytest.MonkeyPatch) -> None:
    namespace = entry(monkeypatch)
    obj = instance(namespace, maintenance=False)
    with pytest.raises(ValueError, match="maintenance"):
        asyncio.run(obj.recovery("inspect"))
    obj.env.SWAY_RECOVERY_MAINTENANCE = "true"
    for operation in ("bookmark", "restore", "restart"):
        with pytest.raises(ValueError, match="object ID"):
            asyncio.run(obj.recovery(operation, "wrong-object", "bookmark"))
    obj.ctx.storage.onNextSessionRestoreBookmark.assert_not_called()
    obj.ctx.abort.assert_not_called()
    assert asyncio.run(obj.recovery("bookmark", "a" * 64)) == "bookmark"
    assert asyncio.run(obj.recovery("restore", "a" * 64, "saved")) == "undo"
    obj.ctx.storage.onNextSessionRestoreBookmark.assert_awaited_once_with("saved")


def test_maintenance_blocks_http_and_defers_bots(monkeypatch: pytest.MonkeyPatch) -> None:
    namespace = entry(monkeypatch)
    obj = instance(namespace, maintenance=True)
    assert asyncio.run(obj.fetch(None))[1] == 503
    assert asyncio.run(obj.fetch(None))[2]["Cache-Control"] == "no-store"
    asyncio.run(obj.alarm())
    obj.runtime.service.pending_bot_games.assert_not_called()
    obj.ctx.storage.setAlarm.assert_awaited_once()
    worker = namespace["Default"].__new__(namespace["Default"])
    worker.env = obj.env
    assert asyncio.run(worker.fetch(None))[1] == 503
    worker.env.SWAY_RECOVERY_MAINTENANCE = "false"
    with pytest.raises(ValueError, match="maintenance"):
        asyncio.run(worker.recovery("inspect"))


def test_snapshot_covers_new_tables_without_exposing_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    obj = instance(entry(monkeypatch), maintenance=True)
    schema = [{"type": "table", "name": "new_table", "sql": "CREATE TABLE new_table (secret TEXT)"}]
    rows = [{"secret": "sensitive-token"}, {"secret": "another-token"}]

    def execute(query: str) -> SimpleNamespace:
        return SimpleNamespace(toArray=lambda: schema if "sqlite_master" in query else rows)

    obj.ctx.storage.sql = SimpleNamespace(exec=execute)
    initial = asyncio.run(obj.recovery("inspect"))
    assert initial["counts"] == {"new_table": 2}
    assert "sensitive-token" not in str(initial)
    rows.reverse()
    assert asyncio.run(obj.recovery("inspect")) == initial
    rows[0]["secret"] = "rotated-token"
    assert asyncio.run(obj.recovery("inspect"))["digest"] != initial["digest"]


def test_controller_preserves_undo_across_lost_restore_response(tmp_path: Path) -> None:
    """The real Node controller talks to a deterministic fake RPC transport."""
    import json
    import os
    import subprocess

    source = ENTRY.parent.parent / "recovery/installation.mjs"
    controller = tmp_path / "installation.mjs"
    controller.write_text(source.read_text())
    package = tmp_path / "node_modules/wrangler"
    package.mkdir(parents=True)
    (package / "package.json").write_text('{"type":"module","exports":"./index.mjs"}')
    (package / "index.mjs").write_text(
        """
import {readFile, writeFile} from 'node:fs/promises';
export async function getPlatformProxy() {
  const file = process.env.FAKE_STATE;
  return {dispose: async () => {}, env: {INSTALLATION: {recovery: async (op,id,bookmark) => {
    const state = JSON.parse(await readFile(file, 'utf8'));
    if (op === 'inspect') return state.current;
    if (id !== state.current.objectId) throw Error('wrong object');
    if (op === 'bookmark') return state.current.digest;
    if (op === 'restore') {
      state.current = state.history[bookmark];
      await writeFile(file, JSON.stringify(state));
      if (process.env.FAIL_RESTORE === 'true') throw Error('lost response after restore');
      return 'returned-undo';
    }
    if (op === 'restart') throw Error('abort');
  }}}};
}
"""
    )
    state_file = tmp_path / "remote.json"
    object_id = "a" * 64
    before = {"objectId": object_id, "digest": "bbb", "counts": {"sessions": 2}}
    desired = {"objectId": object_id, "digest": "aaa", "counts": {"sessions": 1}}
    state_file.write_text(
        json.dumps({"current": before, "history": {"aaa": desired, "bbb": before}})
    )
    config = tmp_path / "client.json"
    config.write_text(
        json.dumps(
            {
                "account_id": "c" * 32,
                "services": [{"binding": "INSTALLATION", "service": "pilot", "remote": True}],
            }
        )
    )
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {
                "target": {"account": "c" * 32, "worker": "pilot"},
                "state": desired,
                "bookmark": "aaa",
            }
        )
    )
    receipt = tmp_path / "receipt.json"
    environment = dict(os.environ, CLOUDFLARE_ACCOUNT_ID="c" * 32, SWAY_RECOVERY_TARGET="pilot")
    environment["FAKE_STATE"] = str(state_file)

    def run(command: str, *files: Path, fail: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["node", str(controller), command, str(config), *(str(file) for file in files)],
            env=dict(environment, FAIL_RESTORE=str(fail).lower()),
            text=True,
            capture_output=True,
            check=False,
        )

    failed = run("restore", baseline, receipt, fail=True)
    assert failed.returncode != 0
    assert "lost response" in failed.stderr
    checkpoint = json.loads(receipt.read_text())
    assert checkpoint["before"]["state"] == before
    assert receipt.stat().st_mode & 0o777 == 0o600
    resumed = run("restore", baseline, receipt)
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(receipt.read_text())["before"]["state"] == before
    undone = run("undo", receipt)
    assert undone.returncode == 0, undone.stderr
    assert json.loads(state_file.read_text())["current"] == before
    environment["CLOUDFLARE_ACCOUNT_ID"] = "d" * 32
    rejected = run("restore", baseline, tmp_path / "wrong-account.json")
    assert rejected.returncode != 0
    assert not (tmp_path / "wrong-account.json").exists()
    assert json.loads(state_file.read_text())["current"] == before
