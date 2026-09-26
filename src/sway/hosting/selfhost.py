"""Laptop/VM adapters: private SQLite, a process lock and bounded worker threads."""

from __future__ import annotations

import time
from collections import deque
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from threading import Lock

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from sway.hosting.config import HostedConfig
from sway.hosting.dispatcher import BotDispatcher
from sway.hosting.identity import IdentityService
from sway.hosting.service import HostedService
from sway.hosting.storage import HostedStore
from sway.hosting.web import create_application
from sway.presentation.themes import STATIC_ROOT


class LocalRateLimiter:
    """Bounded process-local budgets; shared by all requests in this server."""

    def __init__(self, max_keys: int) -> None:
        self.max_keys = max_keys
        self.buckets: dict[tuple[str, str], deque[float]] = {}
        self.lock = Lock()

    def allow(self, peer: str, category: str, limit: int) -> bool:
        now = time.monotonic()
        with self.lock:
            for key in tuple(self.buckets):
                bucket = self.buckets[key]
                while bucket and bucket[0] <= now - 60:
                    bucket.popleft()
                if not bucket:
                    del self.buckets[key]
            key = (peer, category)
            if key not in self.buckets and len(self.buckets) >= self.max_keys:
                return False
            bucket = self.buckets.setdefault(key, deque())
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True


class SelfHostedRuntime:
    def __init__(self, config: HostedConfig) -> None:
        self.config = config
        config.prepare_directory()
        self.store = HostedStore(config.database_path)
        self.identity = IdentityService(self.store)
        self.service = HostedService(self.store)
        self.dispatcher = BotDispatcher(self.service)
        self.limiter = LocalRateLimiter(config.max_rate_limit_keys)
        self.assets = StaticFiles(directory=STATIC_ROOT)

    def clock(self) -> float:
        return self.store.clock()

    async def execute[**P, T](
        self, operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> T:
        return await run_in_threadpool(operation, *args, **kwargs)

    async def notify(self, game_id: str) -> None:
        self.dispatcher.enqueue(game_id)

    @asynccontextmanager
    async def lifespan(self, _app: FastAPI) -> AsyncGenerator[None]:
        with self.config.process_lock():
            self.dispatcher.start()
            try:
                yield
            finally:
                self.dispatcher.stop()


def create_selfhost_app(config: HostedConfig | None = None) -> FastAPI:
    settings = config or HostedConfig.from_env()
    return create_application(settings.web_config(), SelfHostedRuntime(settings))
