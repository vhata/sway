"""Local-only real-runtime contracts. Never use this configuration for deployment."""

import asyncio
import time

from cloudflare_runtime import Installation, Runtime
from contract_checks import run
from workers import DurableObject, Response, WorkerEntrypoint

from sway.bots import BotState, choose
from sway.hosting.runtime import WebConfig


class Contracts(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.runtime = Runtime(ctx, WebConfig("https://localhost:8798"))

    async def fetch(self, request):
        if request.url.endswith("/bot/start"):
            return await self.start_bot()
        if request.url.endswith("/bot/status"):
            game = self.ctx.storage.kv.get("bot_game")
            revision = self.ctx.storage.kv.get("bot_revision")
            current = self.ctx.storage.sql.exec(
                "SELECT revision FROM hosted_rooms WHERE game_id=?", game
            ).one()["revision"]
            return Response.json({"progressed": current > revision})
        checks = await self.runtime.execute(run, self.runtime.store)
        sql = self.ctx.storage.sql
        sql.exec("CREATE TABLE IF NOT EXISTS alarm_contract (value INTEGER)")
        sql.exec("DELETE FROM alarm_contract")

        async def fail(_txn):
            self.ctx.storage.transactionSync(
                lambda: sql.exec("INSERT INTO alarm_contract VALUES (7)")
            )
            await self.ctx.storage.setAlarm(int(time.time() * 1000) + 1000)
            raise ValueError("injected scheduling transaction failure")

        try:
            await self.ctx.storage.transaction(fail)
        except Exception:
            pass
        assert sql.exec("SELECT * FROM alarm_contract").toArray() == []
        assert await self.ctx.storage.getAlarm() is None
        checks.append("SQL and alarm roll back together")

        async def increment(_txn):
            value = sql.exec("SELECT COUNT(*) AS n FROM alarm_contract").one()["n"]
            await asyncio.sleep(0)
            sql.exec("INSERT INTO alarm_contract VALUES (?)", value)

        await asyncio.gather(*(self.ctx.storage.transaction(increment) for _ in range(4)))
        values = [
            row["value"]
            for row in sql.exec("SELECT value FROM alarm_contract ORDER BY value").toArray()
        ]
        assert values == [0, 1, 2, 3], values
        checks.append("concurrent async transactions serialize")
        sql.exec("DELETE FROM alarm_contract")
        await self.ctx.storage.setAlarm(int(time.time() * 1000) + 100)
        return Response.json({"checks": checks})

    async def start_bot(self):
        identity, service = self.runtime.identity, self.runtime.service
        anonymous = await self.runtime.execute(identity.anonymous_session)
        user = await self.runtime.execute(identity.create_principal, anonymous.token, "Bot test")
        token = user.session.token
        table = await self.runtime.execute(service.create, token, ("human", "economy"))
        table = await self.runtime.execute(
            service.ready, token, table.game_id, table.lobby_revision
        )
        table = await self.runtime.execute(
            service.start, token, table.game_id, table.lobby_revision
        )
        for number in range(100):
            if table.pending_player == 1:
                self.ctx.storage.kv.put("bot_game", table.game_id)
                self.ctx.storage.kv.put("bot_revision", table.revision)
                assert await self.ctx.storage.getAlarm() is not None
                # Hold this test job long enough to kill workerd with pending work.
                await self.ctx.storage.setAlarm(int(time.time() * 1000) + 3000)
                return Response.json({"pending": True})
            assert table.view is not None and table.view.pending is not None
            command = choose(table.view, table.view.pending, BotState("engine", number)).command
            result = await self.runtime.execute(
                service.submit, token, table.game_id, f"bot-{number}", command
            )
            table = result.table
        raise AssertionError("Failed to reach bot turn")

    async def alarm(self):
        self.ctx.storage.sql.exec("CREATE TABLE IF NOT EXISTS alarm_contract (value INTEGER)")
        self.ctx.storage.sql.exec("INSERT INTO alarm_contract VALUES (100)")
        await Installation.alarm(self)

    async def alarm_fired(self):
        return (
            self.ctx.storage.sql.exec(
                "SELECT COUNT(*) AS n FROM alarm_contract WHERE value=100"
            ).one()["n"]
            > 0
        )


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        if request.url.endswith("/health"):
            return Response.json({"run": self.env.CONTRACT_RUN})
        name = "bots" if "/bot/" in request.url else "contracts"
        obj = self.env.CONTRACTS.getByName(name)
        if request.url.endswith("/alarm"):
            return Response.json({"fired": await obj.alarm_fired()})
        return await obj.fetch(request)
