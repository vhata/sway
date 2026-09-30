"""Bounded synthetic request measurements; loopback only, never a live load test."""

from __future__ import annotations

import asyncio
import json
import math
import statistics
import sys
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx


@dataclass
class Form:
    action: str
    hidden: dict[str, str] = field(default_factory=dict)


class Document(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__()
        self.forms: list[Form] = []
        self.table: dict[str, str] = {}
        self.current: Form | None = None
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        if values.get("id") == "table":
            self.table = values
        if tag == "form":
            self.current = Form(values.get("action", ""))
            self.forms.append(self.current)
        elif tag == "input" and self.current and values.get("type") == "hidden":
            self.current.hidden[values["name"]] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self.current = None

    def form(self, action: str) -> dict[str, str]:
        return next(form.hidden for form in self.forms if form.action == action)


async def measure(origin: str) -> None:
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Capacity measurement requires an isolated HTTPS loopback origin")
    tables: list[str] = []
    versions: dict[str, str] = {}
    # Only this loopback-only harness accepts the local self-signed certificate.
    async with httpx.AsyncClient(
        base_url=origin,
        verify=False,
        trust_env=False,
        timeout=30,
        headers={"Origin": origin},
        follow_redirects=False,
    ) as client:

        async def get(path: str) -> Document:
            response = await client.get(path)
            response.raise_for_status()
            return Document(response.text)

        async def post(path: str, data: dict[str, str]) -> Document:
            response = await client.post(path, data=data)
            response.raise_for_status()
            return Document(response.text)

        account = await get("/account")
        await post("/identity", {**account.form("/identity"), "display_name": "Capacity probe"})
        account = await get("/account")
        csrf = account.form("/logout")["csrf"]
        try:
            for _ in range(8):
                response = await client.post(
                    "/games",
                    data={
                        "csrf": csrf,
                        "players": "2",
                        "controller1": "economy",
                        "supply": "starter",
                    },
                )
                assert response.status_code == 303, response.status_code
                path = response.headers["location"]
                assert path.startswith("/games/") and "?" not in path
                tables.append(path)
                document = await get(path)
                document = await post(
                    path + "/ready",
                    {
                        **document.form(path + "/ready"),
                        "ready": "true",
                    },
                )
                document = await post(path + "/start", document.form(path + "/start"))
                versions[path] = document.table["data-preference-version"]
            # Let the initial bot turns settle; this is not a bot throughput test.
            await asyncio.sleep(2)
            for concurrency in (1, 4, 8):
                for kind in ("page", "poll", "theme"):
                    latencies: list[float] = []
                    statuses: list[int] = []

                    async def request(path: str, turn: int, workload: str) -> tuple[float, int]:
                        started = time.perf_counter()
                        if workload == "theme":
                            response = await client.post(
                                path + "/theme",
                                data={
                                    "csrf": csrf,
                                    "theme": "orbital" if turn % 2 else "common-ground",
                                    "preference_version": versions[path],
                                },
                            )
                        elif workload == "poll":
                            # A deliberately stale revision exercises rendered poll updates.
                            response = await client.get(path + "/updates?revision=-1")
                        else:
                            response = await client.get(path)
                        latency = (time.perf_counter() - started) * 1000
                        response.raise_for_status()
                        assert 'id="table"' in response.text
                        document = Document(response.text)
                        versions[path] = document.table["data-preference-version"]
                        return latency, response.status_code

                    started = time.perf_counter()
                    for turn in range(3):
                        results = await asyncio.gather(
                            *(request(path, turn, kind) for path in tables[:concurrency])
                        )
                        for latency, status in results:
                            latencies.append(latency)
                            statuses.append(status)
                    elapsed = time.perf_counter() - started
                    ordered = sorted(latencies)
                    print(
                        json.dumps(
                            {
                                "workload": kind,
                                "concurrency": concurrency,
                                "requests": len(latencies),
                                "seconds": round(elapsed, 3),
                                "requests_per_second": round(len(latencies) / elapsed, 2),
                                "median_ms": round(statistics.median(latencies), 2),
                                "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 2),
                                "max_ms": round(max(latencies), 2),
                                "statuses": sorted(set(statuses)),
                            }
                        ),
                        flush=True,
                    )
        finally:
            for path in tables:
                await post(path + "/cancel", {"csrf": csrf})
            response = await client.post("/logout", data={"csrf": csrf})
            assert response.status_code == 303, response.status_code
        print("Capacity: eight synthetic tables cancelled; local measurements only", flush=True)


if __name__ == "__main__":
    asyncio.run(measure(sys.argv[1]))
