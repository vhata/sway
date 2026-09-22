"""Probe an installed wheel from outside its checkout and editable environment."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from importlib import import_module
from importlib.metadata import version
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from starlette.types import Message, Scope


async def request(application: FastAPI, path: str) -> bytes:
    sent: list[Message] = []
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"localhost")],
        "server": ("localhost", 80),
        "client": ("127.0.0.1", 12345),
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    await application(scope, receive, send)
    starts = [message for message in sent if message["type"] == "http.response.start"]
    if len(starts) != 1 or starts[0].get("status") != 200:
        raise RuntimeError(f"Installed application did not serve {path}: {starts}")
    chunks: list[bytes] = []
    for message in sent:
        if message["type"] == "http.response.body":
            body = cast(object, message.get("body", b""))
            if not isinstance(body, bytes):
                raise RuntimeError("ASGI response body was not bytes.")
            chunks.append(body)
    result = b"".join(chunks)
    if not result:
        raise RuntimeError(f"Installed application served an empty response for {path}.")
    return result


async def main() -> None:
    package_file = import_module("sway").__file__
    if package_file is None:
        raise RuntimeError("The installed package has no file location.")
    package = Path(package_file).resolve().parent
    if not package.is_relative_to(Path(sys.prefix).resolve()):
        raise RuntimeError(f"Smoke check imported an editable/source package: {package}")
    static = package / "static"
    required = (
        "app.js",
        "style.css",
        "themes/neutral.json",
        "themes/orbital.json",
        "vendor/HTMX-LICENSE",
    )
    for name in required:
        if not (static / name).is_file():
            raise RuntimeError(f"Wheel is missing required asset: {name}")
    htmx = list((static / "vendor").glob("htmx-*.min.js"))
    if len(htmx) != 1:
        raise RuntimeError("Wheel must contain its pinned HTMX runtime.")
    catalog = cast(dict[str, object], import_module("sway.engine").CATALOG)
    load_themes = cast(
        Callable[[frozenset[str]], dict[str, object]],
        import_module("sway.presentation.themes").load_themes,
    )
    if not {"neutral", "orbital"} <= load_themes(frozenset(catalog)).keys():
        raise RuntimeError("Both bundled themes must load with complete card and image coverage.")
    create_app = cast(Callable[[Path], FastAPI], import_module("sway.web").create_app)
    application = create_app(Path.cwd() / "data")
    homepage = await request(application, "/")
    if b"htmx-" not in homepage:
        raise RuntimeError("Installed homepage does not reference its HTMX runtime.")
    for name in ("app.js", "style.css", f"vendor/{htmx[0].name}"):
        await request(application, f"/static/{name}")
    print(
        f"Installed sway-game {version('sway-game')}: homepage, both themes, images, CSS, JS and HTMX passed."
    )


if __name__ == "__main__":
    asyncio.run(main())
