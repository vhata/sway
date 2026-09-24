"""SQLite transaction boundary for hosted identity and multiplayer records."""

from __future__ import annotations

import os
import sqlite3
import stat
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from sway.storage import SaveFormatError

APPLICATION_ID = 0x53575948
SCHEMA_VERSION = 1


class HostedStore:
    """A hosted-only database; callers compose authorization and writes atomically.

    The injectable clock returns seconds since the Unix epoch. Connections never
    outlive their transaction. Do not run executescript within a transaction: the
    sqlite3 driver implicitly commits it.
    """

    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time) -> None:
        self.path = path
        self.clock = clock
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077:
            raise SaveFormatError(
                "Hosted database must be an owner-only regular file, not a symlink."
            )
        with self.transaction(write=True) as conn:
            app_id = cast(int, conn.execute("PRAGMA application_id").fetchone()[0])
            version = cast(int, conn.execute("PRAGMA user_version").fetchone()[0])
            existing = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if app_id not in (0, APPLICATION_ID) or (app_id == 0 and (existing or version)):
                raise SaveFormatError(
                    "This is not a hosted Sway database; local saves are separate."
                )
            if version not in (0, SCHEMA_VERSION):
                raise SaveFormatError(f"Unsupported hosted database version: {version}.")
            if version == 0:
                for statement in _SCHEMA:
                    conn.execute(statement)
                conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            else:
                row = conn.execute(
                    "SELECT version FROM hosting_schema WHERE component = 'identity'"
                ).fetchone()
                if row is None or row[0] != SCHEMA_VERSION:
                    raise SaveFormatError("Unsupported hosted identity schema version.")

    @contextmanager
    def transaction(self, *, write: bool = False) -> Generator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            if not write:
                conn.execute("PRAGMA query_only = ON")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        finally:
            conn.close()


_SCHEMA = (
    "CREATE TABLE hosting_schema (component TEXT PRIMARY KEY, version INTEGER NOT NULL)",
    "INSERT INTO hosting_schema VALUES ('identity', 1)",
    """CREATE TABLE principals (
        principal_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        created_at REAL NOT NULL
    )""",
    """CREATE TABLE sessions (
        session_id TEXT PRIMARY KEY,
        token_hash TEXT NOT NULL UNIQUE,
        principal_id TEXT REFERENCES principals(principal_id),
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL
    )""",
    "CREATE INDEX sessions_principal ON sessions(principal_id)",
    """CREATE TABLE recovery_credentials (
        principal_id TEXT PRIMARY KEY REFERENCES principals(principal_id),
        code_hash TEXT NOT NULL UNIQUE
    )""",
)
