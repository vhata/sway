"""Portable web settings and execution ports for both hosted deployments."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from fastapi import FastAPI
from starlette.types import ASGIApp

from sway.hosting.identity import IdentityService
from sway.hosting.service import HostedService


@dataclass(frozen=True)
class WebConfig:
    origin: str
    max_request_bytes: int = 65_536
    mutation_requests_per_minute: int = 60
    credential_requests_per_minute: int = 10
    max_rate_limit_keys: int = 10_000

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.origin)
            host, port = parsed.hostname, parsed.port
        except ValueError as exc:
            raise ValueError("SWAY_HOSTED_ORIGIN must be a canonical HTTPS origin") from exc
        if (
            parsed.scheme != "https"
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or not self.origin.isascii()
            or any(character.isspace() for character in self.origin)
        ):
            raise ValueError("SWAY_HOSTED_ORIGIN must be a canonical HTTPS origin without a path")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if len(host) > 253 or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")
            ):
                raise ValueError("SWAY_HOSTED_ORIGIN has an invalid host") from None
            authority = host
        else:
            authority = f"[{address.compressed}]" if address.version == 6 else str(address)
        if port is not None and port != 443:
            if port == 0:
                raise ValueError("SWAY_HOSTED_ORIGIN has an invalid port")
            authority += f":{port}"
        if self.origin != f"https://{authority}":
            raise ValueError("SWAY_HOSTED_ORIGIN must use its canonical spelling (no default port)")
        for name in (
            "max_request_bytes",
            "mutation_requests_per_minute",
            "credential_requests_per_minute",
            "max_rate_limit_keys",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    @property
    def canonical_host(self) -> str:
        return urlsplit(self.origin).netloc


class RateLimiter(Protocol):
    def allow(self, peer: str, category: str, limit: int) -> bool: ...


class HostedRuntime(Protocol):
    """Runtime owns execution/lifecycle; services own complete atomic operations."""

    @property
    def identity(self) -> IdentityService: ...
    @property
    def service(self) -> HostedService: ...
    @property
    def limiter(self) -> RateLimiter: ...
    @property
    def assets(self) -> ASGIApp | None: ...

    def clock(self) -> float: ...
    async def execute[**P, T](
        self, operation: Callable[P, T], *args: P.args, **kwargs: P.kwargs
    ) -> T: ...
    async def notify(self, game_id: str) -> None: ...
    def lifespan(self, app: FastAPI, /) -> AbstractAsyncContextManager[None]: ...
