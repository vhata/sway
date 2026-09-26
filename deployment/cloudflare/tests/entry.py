"""Local-only real-runtime contracts. Never use this configuration for deployment."""

import asyncio
import time

from cloudflare_runtime import Runtime
from contract_checks import run
from workers import DurableObject, Response, WorkerEntrypoint

from sway.hosting.runtime import WebConfig


class Contracts(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.runtime = Runtime(ctx, WebConfig("https://localhost:8798"))

    async def fetch(self, request):
        checks = await self.runtime.execute(run, self.runtime.store)
        sql = self.ctx.storage.sql
        sql.exec("CREATE TABLE IF NOT EXISTS alarm_contract (value INTEGER)")

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

    async def alarm(self):
        self.ctx.storage.sql.exec("INSERT INTO alarm_contract VALUES (100)")

    async def alarm_fired(self):
        return (
            self.ctx.storage.sql.exec(
                "SELECT COUNT(*) AS n FROM alarm_contract WHERE value=100"
            ).one()["n"]
            > 0
        )


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        obj = self.env.CONTRACTS.getByName("contracts")
        if request.url.endswith("/alarm"):
            return Response.json({"fired": await obj.alarm_fired()})
        return await obj.fetch(request)
