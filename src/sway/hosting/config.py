"""Fail-closed settings for the separate, single-process hosted application."""

from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from sway.hosting.runtime import WebConfig


def _local_directory() -> Path:
    return Path(os.environ.get("SWAY_DATA_DIR", str(Path.home() / ".local/share/sway")))


@dataclass(frozen=True)
class HostedConfig:
    """Validated settings; forwarded headers are deliberately never trusted."""

    origin: str
    data_dir: Path
    local_data_dir: Path = field(default_factory=_local_directory)
    max_request_bytes: int = 65_536
    mutation_requests_per_minute: int = 60
    credential_requests_per_minute: int = 10
    max_rate_limit_keys: int = 10_000
    trusted_proxy_ips: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.web_config()
        hosted, local = (
            self.data_dir.expanduser().resolve(),
            self.local_data_dir.expanduser().resolve(),
        )
        if hosted == local or hosted in local.parents or local in hosted.parents:
            raise ValueError(
                "Hosted and local data directories must be separate and non-overlapping"
            )
        object.__setattr__(self, "data_dir", hosted)
        object.__setattr__(self, "local_data_dir", local)
        if self.trusted_proxy_ips:
            raise ValueError("Forwarded headers are unsupported; preserve Host at the TLS proxy")

    def web_config(self) -> WebConfig:
        return WebConfig(
            origin=self.origin,
            max_request_bytes=self.max_request_bytes,
            mutation_requests_per_minute=self.mutation_requests_per_minute,
            credential_requests_per_minute=self.credential_requests_per_minute,
            max_rate_limit_keys=self.max_rate_limit_keys,
        )

    @property
    def canonical_host(self) -> str:
        """Host header authority, including a configured nonstandard port."""
        return urlsplit(self.origin).netloc

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        """Hostname-only allowlist, suitable for TrustedHostMiddleware."""
        return (urlsplit(self.origin).hostname or "",)

    @property
    def database_path(self) -> Path:
        return self.data_dir / "hosted.sqlite3"

    def prepare_directory(self) -> None:
        """Create private storage, rejecting an existing permissive directory."""
        self.data_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.data_dir.stat().st_mode & 0o077:
            raise ValueError("Hosted data directory must be owner-only (chmod 700)")

    @contextmanager
    def process_lock(self) -> Generator[None]:
        """Hold an OS lock for the application lifetime; crashes release it.

        Never unlink this file: replacing its inode would permit two owners.
        """
        self.prepare_directory()
        descriptor = os.open(
            self.data_dir / ".server.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
                raise ValueError("Hosted process lock must be an owner-only regular file")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError(
                    "Another hosted process already owns this data directory"
                ) from None
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> HostedConfig:
        env = os.environ if environ is None else environ
        origin, directory = env.get("SWAY_HOSTED_ORIGIN"), env.get("SWAY_HOSTED_DATA_DIR")
        if not origin or not directory:
            raise ValueError("SWAY_HOSTED_ORIGIN and SWAY_HOSTED_DATA_DIR are required")
        return cls(
            origin=origin,
            data_dir=Path(directory),
            local_data_dir=Path(env.get("SWAY_DATA_DIR", str(Path.home() / ".local/share/sway"))),
            max_request_bytes=int(env.get("SWAY_HOSTED_MAX_REQUEST_BYTES", "65536")),
            mutation_requests_per_minute=int(env.get("SWAY_HOSTED_MUTATIONS_PER_MINUTE", "60")),
            credential_requests_per_minute=int(env.get("SWAY_HOSTED_CREDENTIALS_PER_MINUTE", "10")),
            max_rate_limit_keys=int(env.get("SWAY_HOSTED_MAX_RATE_LIMIT_KEYS", "10000")),
            trusted_proxy_ips=tuple(filter(None, env.get("SWAY_TRUSTED_PROXY_IPS", "").split(","))),
        )
