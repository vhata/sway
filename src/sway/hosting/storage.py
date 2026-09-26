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

from sway.hosting.schema import initialize_identity
from sway.hosting.state import SqlResult, SqlSession, SqlValue
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
                initialize_identity(SQLiteSession(conn))
                conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            else:
                row = conn.execute(
                    "SELECT version FROM hosting_schema WHERE component = 'identity'"
                ).fetchone()
                if row is None or row[0] != SCHEMA_VERSION:
                    raise SaveFormatError("Unsupported hosted identity schema version.")

    def read[T](self, operation: Callable[[SqlSession], T]) -> T:
        with self.transaction() as connection:
            return operation(SQLiteSession(connection))

    def write[T](self, operation: Callable[[SqlSession], T]) -> T:
        with self.transaction(write=True) as connection:
            return operation(SQLiteSession(connection))

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


class SQLiteSession:
    """Materialize values inside the transaction; never expose SQLite cursors."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def execute(self, sql: str, parameters: tuple[SqlValue, ...] = ()) -> SqlResult:
        cursor = self._connection.execute(sql, parameters)
        rows = tuple(cast(dict[str, SqlValue], dict(row)) for row in cursor.fetchall())
        return SqlResult(rows, max(0, cursor.rowcount))
