"""Cloudflare owns transport and lifecycle; shared Sway owns application behaviour."""

import time
from contextlib import asynccontextmanager

from starlette.responses import Response as ASGIResponse
from workers import DurableObject, Response, WorkerEntrypoint, asgi

from sway.hosting.cloudflare_state import DurableStateStore
from sway.hosting.identity import IdentityService
from sway.hosting.runtime import WebConfig
from sway.hosting.schema import initialize_identity
from sway.hosting.service import HostedService
from sway.hosting.web import create_application


class DurableRateLimiter:
    def __init__(self, store, maximum):
        self.store = store
        self.maximum = maximum
        store.write(
            lambda sql: sql.execute(
                "CREATE TABLE IF NOT EXISTS request_limits (peer TEXT, category TEXT, window INTEGER, count INTEGER, PRIMARY KEY(peer, category))"
            )
        )

    def allow(self, peer, category, limit):
        now = int(self.store.clock())

        def operation(sql):
            sql.execute("DELETE FROM request_limits WHERE window <= ?", (now - 60,))
            row = sql.execute(
                "SELECT window, count FROM request_limits WHERE peer=? AND category=?",
                (peer, category),
            ).one()
            if row is None:
                count = sql.execute("SELECT COUNT(*) AS count FROM request_limits").one()["count"]
                if count >= self.maximum:
                    return False
                sql.execute("INSERT INTO request_limits VALUES (?, ?, ?, 1)", (peer, category, now))
                return True
            if row["count"] >= limit:
                return False
            sql.execute(
                "UPDATE request_limits SET count=count+1 WHERE peer=? AND category=?",
                (peer, category),
            )
            return True

        return self.store.write(operation)


class Assets:
    def __init__(self, binding):
        self.binding = binding

    async def __call__(self, scope, receive, send):
        if scope["method"] not in {"GET", "HEAD"}:
            await ASGIResponse(status_code=405)(scope, receive, send)
            return
        response = await self.binding.fetch("https://assets.invalid" + scope["path"])
        body = b"" if scope["method"] == "HEAD" else await response.bytes()
        await ASGIResponse(body, response.status, dict(response.headers))(scope, receive, send)


class Runtime:
    def __init__(self, ctx, settings, assets=None):
        self.assets = Assets(assets) if assets is not None else None
        self.ctx = ctx
        self.store = DurableStateStore(ctx.storage)
        self.store.write(initialize_identity)
        self.identity = IdentityService(self.store)
        self.service = HostedService(self.store)
        self.limiter = DurableRateLimiter(self.store, settings.max_rate_limit_keys)
        self.clock = self.store.clock

    async def execute(self, operation, *args, **kwargs):
        result = []
        failure = []

        async def transaction(_txn):
            try:
                result[:] = [operation(*args, **kwargs)]
                if self.service.pending_bot_games():
                    # SQL pending marker and its wake-up commit together, including
                    # an existing alarm: no crash window between the two writes.
                    if await self.ctx.storage.getAlarm() is None:
                        await self.ctx.storage.setAlarm(int(self.clock() * 1000) + 100)
            except BaseException as exc:
                failure.append(exc)
                raise

        try:
            await self.ctx.storage.transaction(transaction)
        except BaseException:
            if failure:
                raise failure[0] from None
            raise
        return result[0]

    async def notify(self, game_id):
        # execute already commits the durable wake-up with the domain mutation.
        pass

    @asynccontextmanager
    async def lifespan(self, _app):
        yield


class Installation(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.settings = WebConfig(
            env.SWAY_HOSTED_ORIGIN,
            max_request_bytes=int(getattr(env, "SWAY_HOSTED_MAX_REQUEST_BYTES", "65536")),
            mutation_requests_per_minute=int(
                getattr(env, "SWAY_HOSTED_MUTATIONS_PER_MINUTE", "60")
            ),
            credential_requests_per_minute=int(
                getattr(env, "SWAY_HOSTED_CREDENTIALS_PER_MINUTE", "10")
            ),
            max_rate_limit_keys=int(getattr(env, "SWAY_HOSTED_MAX_RATE_LIMIT_KEYS", "10000")),
        )
        self.runtime = Runtime(ctx, self.settings, env.ASSETS)
        self.app = create_application(self.settings, self.runtime)

    async def fetch(self, request):
        # This header is overwritten by Default using Cloudflare's trusted peer.
        peer = request.headers.get("x-sway-peer") or "unknown"

        async def application(scope, receive, send):
            if scope["type"] == "http":
                scope["client"] = (peer, 0)
            await self.app(scope, receive, send)

        return await asgi.fetch(application, request, self.env)

    async def alarm(self):
        # Bound work per invocation. At-least-once delivery is safe because the
        # service commits each bot decision with its expected revision.
        for game_id in self.runtime.service.pending_bot_games()[:4]:
            await self.runtime.execute(self.runtime.service.step_bots, game_id)
        if self.runtime.service.pending_bot_games():
            await self.ctx.storage.setAlarm(int(time.time() * 1000) + 100)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from js import Request

        forwarded = Request.new(request.js_object)
        forwarded.headers.set("x-sway-peer", request.headers.get("cf-connecting-ip") or "unknown")
        try:
            return await self.env.INSTALLATION.getByName("installation").fetch(forwarded)
        except Exception as exc:
            print(f"Request failed ({type(exc).__name__}).")
            return Response("Internal server error.", status=500)
