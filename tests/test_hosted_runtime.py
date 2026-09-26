"""The shared hosted application works without threadpool or server lifecycle calls."""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import anyio.to_thread
import httpx
import pytest
from fastapi import FastAPI

from sway.hosting.identity import IdentityService
from sway.hosting.runtime import WebConfig
from sway.hosting.service import HostedService
from sway.hosting.storage import HostedStore
from sway.hosting.web import COOKIE, create_application


class InlineRuntime:
    """A real state backend with inline execution, as required inside a Worker."""

    assets = None

    def __init__(self, path: Path) -> None:
        self.store = HostedStore(path)
        self.identity = IdentityService(self.store)
        self.service = HostedService(self.store)
        self.limiter = self
        self.notifications: list[str] = []

    def allow(self, peer: str, category: str, limit: int) -> bool:
        return True

    def clock(self) -> float:
        return self.store.clock()

    async def execute[**P, T](
        self, operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> T:
        return operation(*args, **kwargs)

    async def notify(self, game_id: str) -> None:
        self.notifications.append(game_id)

    @asynccontextmanager
    async def lifespan(self, _app: FastAPI) -> AsyncGenerator[None]:
        yield


def test_shared_application_import_does_not_load_selfhost_runtime() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.modules['fcntl'] = None; "
            "from sway.hosting.web import create_application; "
            "assert 'sway.hosting.selfhost' not in sys.modules; "
            "assert 'sway.hosting.dispatcher' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_inline_runtime_supports_private_identity_lobby_and_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_thread(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Shared routes must not invoke a threadpool")

    monkeypatch.setattr(anyio.to_thread, "run_sync", forbidden_thread)
    runtime = InlineRuntime(tmp_path / "hosted.sqlite3")
    origin = "https://sway.test"
    app = create_application(WebConfig(origin), runtime)

    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=origin, follow_redirects=True
        ) as browser:

            async def submit(path: str, values: dict[str, str]) -> httpx.Response:
                form = await browser.get("/account")
                match = re.search(r'name="csrf" value="([^"]+)"', form.text)
                assert match is not None
                return await browser.post(
                    path, data={"csrf": match[1], **values}, headers={"Origin": origin}
                )

            signup = await submit("/identity", {"display_name": "Alice"})
            assert signup.status_code == 200
            code = re.search(r'<code id="recovery-code">([^<]+)</code>', signup.text)
            assert code is not None
            old_token = browser.cookies[COOKIE]
            created = await submit("/games", {"players": "2"})
            assert created.status_code == 200
            path = created.url.path
            assert path.startswith("/games/")
            table = runtime.service.view(old_token, path.rsplit("/", 1)[1])
            poll = await browser.get(
                path + "/updates",
                params={
                    "revision": table.revision,
                    "lobby_revision": table.lobby_revision,
                    "preference_version": table.preference_version,
                },
            )
            assert poll.status_code == 204
            invited = await submit(path + "/invite", {"seat": "1"})
            assert invited.status_code == 200 and "invitation-link" in invited.text
            assert runtime.notifications == []
            await submit("/logout", {})
            recovered = await submit("/recover", {"recovery_code": code[1]})
            assert recovered.status_code == 200
            assert browser.cookies[COOKIE] != old_token
            assert (await browser.get(path)).status_code == 200
            assert "Alice" in (await browser.get("/")).text

    asyncio.run(exercise())
