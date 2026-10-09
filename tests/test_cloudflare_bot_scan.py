"""Run the Cloudflare entry against a SQLite-backed fake of Durable Object storage.

The fake models only what the entry uses: synchronous SQL, nested
``transactionSync`` rollback, an outer async ``transaction`` that also rolls
back alarm changes, and alarm get/set. Real workerd coverage is in
``scripts/cloudflare-check.sh``.
"""

from __future__ import annotations

import asyncio
import json
import runpy
import sqlite3
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from sway.bots import BotState, choose
from sway.hosting.runtime import WebConfig

ENTRY = Path(__file__).parents[1] / "deployment/cloudflare/src/entry.py"


class Cursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    def toArray(self) -> list[dict[str, object]]:
        return self.rows


class Sql:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def exec(self, statement: str, *parameters: object) -> Cursor:
        return Cursor([dict(row) for row in self.conn.execute(statement, parameters).fetchall()])


class Storage:
    def __init__(self, path: Path) -> None:
        self.conn = sqlite3.connect(path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.sql = Sql(self.conn)
        self.alarm: int | None = None
        self.depth = 0

    def _savepoint(self) -> str:
        self.depth += 1
        name = f"sp{self.depth}"
        self.conn.execute(f"SAVEPOINT {name}")
        return name

    def _rollback(self, name: str) -> None:
        self.conn.execute(f"ROLLBACK TO {name}")
        self.conn.execute(f"RELEASE {name}")

    def transactionSync[T](self, operation: Callable[[], T]) -> T:
        name = self._savepoint()
        try:
            result = operation()
        except BaseException:
            self._rollback(name)
            raise
        finally:
            self.depth -= 1
        self.conn.execute(f"RELEASE {name}")
        return result

    async def transaction(self, operation: Callable[[object], Awaitable[None]]) -> None:
        name, alarm = self._savepoint(), self.alarm
        try:
            await operation(None)
        except BaseException:
            self._rollback(name)
            self.alarm = alarm
            raise
        finally:
            self.depth -= 1
        self.conn.execute(f"RELEASE {name}")

    async def getAlarm(self) -> int | None:
        return self.alarm

    async def setAlarm(self, scheduled: int) -> None:
        self.alarm = scheduled


@pytest.fixture
def entry(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    workers = SimpleNamespace(
        DurableObject=object, WorkerEntrypoint=object, Response=object, asgi=SimpleNamespace()
    )
    monkeypatch.setitem(sys.modules, "workers", cast(Any, workers))

    def seed(_bits: int) -> int:
        return 2

    monkeypatch.setattr("sway.hosting.service.secrets.randbits", seed)
    return runpy.run_path(str(ENTRY))


def test_undecodable_room_neither_fails_requests_nor_stops_alarm_bots(
    tmp_path: Path, entry: dict[str, Any]
) -> None:
    storage = Storage(tmp_path / "durable.sqlite3")
    ctx = SimpleNamespace(storage=storage)
    runtime = entry["Runtime"](ctx, WebConfig("https://localhost"))
    installation = entry["Installation"].__new__(entry["Installation"])
    installation.env = SimpleNamespace(SWAY_RECOVERY_MAINTENANCE="false")
    installation.ctx, installation.runtime = ctx, runtime
    identity, service = runtime.identity, runtime.service
    execute = runtime.execute

    async def account(name: str) -> str:
        anonymous = await execute(identity.anonymous_session)
        return (await execute(identity.create_principal, anonymous.token, name)).session.token

    async def bot_turn(host: str) -> str:
        table = await execute(service.create, host, ("human", "engine"))
        table = await execute(service.ready, host, table.game_id, table.lobby_revision)
        table = await execute(service.start, host, table.game_id, table.lobby_revision)
        for number in range(30):
            if table.pending_player != 0:
                return table.game_id
            assert table.view is not None and table.view.pending is not None
            command = choose(table.view, table.view.pending, BotState("engine", number)).command
            result = await execute(service.submit, host, table.game_id, f"h-{number}", command)
            table = result.table
        raise AssertionError("Failed to reach a bot turn")

    async def scenario() -> None:
        host = await account("Host")
        other = await account("Other")
        healthy = await bot_turn(host)
        broken = await bot_turn(host)
        row = storage.conn.execute(
            "SELECT snapshot,revision FROM hosted_rooms WHERE game_id=?", (broken,)
        ).fetchone()
        payload = json.loads(row["snapshot"])
        payload["schema"] = 99
        snapshot = json.dumps(payload)
        storage.conn.execute(
            "UPDATE hosted_rooms SET snapshot=? WHERE game_id=?", (snapshot, broken)
        )
        storage.alarm = None

        # Operations unrelated to the unreadable room keep working and arm bots.
        anonymous = await execute(identity.anonymous_session)
        assert (await execute(identity.authenticate, anonymous.token)).principal_id is None
        assert (await execute(identity.authenticate, other)).principal_id is not None
        assert await execute(service.list_tables, other) == ()
        await execute(service.create, other, ("human", "human"))
        assert storage.alarm is not None

        for _ in range(50):
            storage.alarm = None
            await installation.alarm()
            if storage.alarm is None:
                break
        assert storage.alarm is None
        table = await execute(service.view, host, healthy)
        assert table.pending_player == 0 and table.bot_paused is None
        paused = storage.conn.execute(
            "SELECT bot_paused,snapshot,revision FROM hosted_rooms WHERE game_id=?", (broken,)
        ).fetchone()
        assert tuple(paused) == ("snapshot_unreadable", snapshot, row["revision"])
        # Nothing remains to wake for: a later request does not re-arm the alarm.
        await execute(identity.anonymous_session)
        assert storage.alarm is None

    asyncio.run(scenario())
