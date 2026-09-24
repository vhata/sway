"""Consistent, private backups and offline restores of the complete hosted DB.

Run with ``uv run --locked python -m sway.hosting.backup backup SOURCE DEST``.
The destination must not exist. Restore uses the same verified copy operation.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import time
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import cast

APPLICATION_ID = 0x53575948
SCHEMA_VERSION = 1


def _verify(connection: sqlite3.Connection) -> None:
    application_id = cast(tuple[int], connection.execute("PRAGMA application_id").fetchone())[0]
    version = cast(tuple[int], connection.execute("PRAGMA user_version").fetchone())[0]
    if application_id != APPLICATION_ID or version != SCHEMA_VERSION:
        raise ValueError("Unsupported hosted database format; the original was left unchanged")
    components = cast(
        list[tuple[str, int]],
        connection.execute("SELECT component, version FROM hosting_schema").fetchall(),
    )
    if dict(components).get("identity") != 1 or any(
        component not in ("identity", "multiplayer") or version != 1
        for component, version in components
    ):
        raise ValueError("Unsupported hosted component schema")
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("Hosted database integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("Hosted database foreign key check failed")


def copy_database(source: Path, destination: Path, *, timeout: float = 30.0) -> Path:
    """Snapshot all tables, including credentials, without copying a live WAL.

    The SQLite backup API provides a consistent snapshot while the server writes.
    An exclusive, mode-0600 destination prevents overwrites and partial failures
    are removed. Restores must target a new filename while the server is stopped.
    """
    if timeout <= 0:
        raise ValueError("Backup timeout must be positive")
    source = source.expanduser().resolve(strict=True)
    destination = destination.expanduser().absolute()
    if not source.is_file() or source.stat().st_mode & 0o077:
        raise ValueError("Source database must be an owner-only regular file (chmod 600)")
    if destination.parent.stat().st_mode & 0o077:
        raise ValueError("Destination directory must be owner-only (chmod 700)")
    sidecars = [Path(str(destination) + suffix) for suffix in ("-journal", "-wal", "-shm")]
    if any(os.path.lexists(sidecar) for sidecar in sidecars):
        raise FileExistsError("Destination SQLite sidecar already exists; choose a new filename")
    deadline = time.monotonic() + timeout

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() >= deadline:
            raise TimeoutError("Database copy timed out; retry during quieter activity")

    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        with closing(
            sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True, timeout=timeout)
        ) as original:
            with closing(sqlite3.connect(destination, timeout=timeout)) as copied:
                original.backup(copied, pages=128, progress=progress, sleep=0.05)
                _verify(copied)
                # A portable self-contained file; no source WAL/SHM needed.
                _ = copied.execute("PRAGMA journal_mode = DELETE").fetchone()
        with destination.open("rb") as completed:
            os.fsync(completed.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        for sidecar in sidecars:
            sidecar.unlink(missing_ok=True)
        raise
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("operation", choices=("backup", "restore"))
    _ = parser.add_argument("source", type=Path)
    _ = parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    source, destination = cast(Path, args.source), cast(Path, args.destination)
    try:
        result = copy_database(source, destination)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"Database copy failed: {exc}\n")
    print(f"Verified database copy: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
