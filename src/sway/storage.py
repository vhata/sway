"""Transactional save storage, independent of rules and presentation.

The Store protocol is also the contract for a future PostgreSQL adapter.
Snapshots and commands are versioned JSON owned by the application/engine.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast


class StorageError(Exception):
    """A save cannot be read or safely changed."""


class StorageConflict(StorageError):
    """Another request already advanced this game."""


class GameNotFound(StorageError):
    """No game exists for the requested identifier."""


class SaveFormatError(StorageError):
    """The save or database uses an unsupported format."""


@dataclass(frozen=True)
class StoredGame:
    game_id: str
    revision: int
    snapshot: str
    metadata: str
    theme_id: str
    status: str
    updated_at: str


@dataclass(frozen=True)
class StoredCommand:
    revision: int
    command_id: str
    command: str
    events: str


class Store(Protocol):
    def create(self, game_id: str, snapshot: str, metadata: str, theme_id: str) -> StoredGame: ...

    def load(self, game_id: str) -> StoredGame: ...

    def list_games(self) -> list[StoredGame]: ...

    def commit(
        self,
        game_id: str,
        expected_revision: int,
        command_id: str,
        snapshot: str,
        command: str,
        events: str,
        status: str = "active",
    ) -> StoredGame: ...

    def set_theme(self, game_id: str, theme_id: str) -> StoredGame: ...

    def history(self, game_id: str) -> list[StoredCommand]: ...


def _validate_json(value: str, expected: type[dict[str, object]] | type[list[object]]) -> None:
    try:
        parsed = cast(object, json.loads(value))
    except (ValueError, TypeError) as exc:
        raise SaveFormatError("Save data must be valid JSON.") from exc
    if not isinstance(parsed, expected):
        raise SaveFormatError(f"Save data must be a JSON {expected.__name__}.")


class SQLiteStore:
    """Open a connection per operation; never hold locks while bots compute."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            row = cast(tuple[int], conn.execute("PRAGMA user_version").fetchone())
            if row[0] not in (0, 1):
                raise SaveFormatError(f"Unsupported database version: {row[0]}.")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS games (
                    game_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL CHECK (revision >= 0),
                    snapshot TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    theme_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commands (
                    game_id TEXT NOT NULL REFERENCES games(game_id),
                    revision INTEGER NOT NULL,
                    command_id TEXT NOT NULL,
                    command TEXT NOT NULL,
                    events TEXT NOT NULL,
                    PRIMARY KEY (game_id, revision),
                    UNIQUE (game_id, command_id)
                );
                PRAGMA user_version = 1;
                """
            )

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.path, timeout=5.0)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _record(row: tuple[str, int, str, str, str, str, str]) -> StoredGame:
        return StoredGame(*row)

    @classmethod
    def _load(cls, conn: sqlite3.Connection, game_id: str) -> StoredGame:
        row = cast(
            tuple[str, int, str, str, str, str, str] | None,
            conn.execute(
                "SELECT game_id, revision, snapshot, metadata, theme_id, status, "
                "updated_at FROM games WHERE game_id = ?",
                (game_id,),
            ).fetchone(),
        )
        if row is None:
            raise GameNotFound(f"Game {game_id!r} was not found.")
        return cls._record(row)

    def create(self, game_id: str, snapshot: str, metadata: str, theme_id: str) -> StoredGame:
        _validate_json(snapshot, dict)
        _validate_json(metadata, dict)
        with self._connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO games VALUES (?, 0, ?, ?, ?, 'active', ?)",
                    (game_id, snapshot, metadata, theme_id, datetime.now(UTC).isoformat()),
                )
            except sqlite3.IntegrityError as exc:
                raise StorageConflict("That game already exists.") from exc
            result = self._load(conn, game_id)
        return result

    def load(self, game_id: str) -> StoredGame:
        with self._connection() as conn:
            return self._load(conn, game_id)

    def list_games(self) -> list[StoredGame]:
        with self._connection() as conn:
            rows = cast(
                list[tuple[str, int, str, str, str, str, str]],
                conn.execute(
                    "SELECT game_id, revision, snapshot, metadata, theme_id, status, "
                    "updated_at FROM games ORDER BY updated_at DESC, game_id"
                ).fetchall(),
            )
            return [self._record(row) for row in rows]

    def commit(
        self,
        game_id: str,
        expected_revision: int,
        command_id: str,
        snapshot: str,
        command: str,
        events: str,
        status: str = "active",
    ) -> StoredGame:
        _validate_json(snapshot, dict)
        _validate_json(command, dict)
        _validate_json(events, list)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = self._load(conn, game_id)
            duplicate = cast(
                tuple[str] | None,
                conn.execute(
                    "SELECT command FROM commands WHERE game_id = ? AND command_id = ?",
                    (game_id, command_id),
                ).fetchone(),
            )
            if duplicate is not None:
                if duplicate[0] != command:
                    raise StorageConflict("Command identifier reused for a different choice.")
                return current
            if current.revision != expected_revision:
                raise StorageConflict("The game advanced. Reload before making your choice.")
            revision = expected_revision + 1
            conn.execute(
                "INSERT INTO commands VALUES (?, ?, ?, ?, ?)",
                (game_id, revision, command_id, command, events),
            )
            conn.execute(
                "UPDATE games SET revision = ?, snapshot = ?, status = ?, updated_at = ? "
                "WHERE game_id = ? AND revision = ?",
                (
                    revision,
                    snapshot,
                    status,
                    datetime.now(UTC).isoformat(),
                    game_id,
                    expected_revision,
                ),
            )
            result = self._load(conn, game_id)
        return result

    def set_theme(self, game_id: str, theme_id: str) -> StoredGame:
        with self._connection() as conn:
            changed = conn.execute(
                "UPDATE games SET theme_id = ? WHERE game_id = ?", (theme_id, game_id)
            )
            if changed.rowcount == 0:
                raise GameNotFound(f"Game {game_id!r} was not found.")
            return self._load(conn, game_id)

    def history(self, game_id: str) -> list[StoredCommand]:
        with self._connection() as conn:
            self._load(conn, game_id)
            rows = cast(
                list[tuple[int, str, str, str]],
                conn.execute(
                    "SELECT revision, command_id, command, events FROM commands "
                    "WHERE game_id = ? ORDER BY revision",
                    (game_id,),
                ).fetchall(),
            )
            return [StoredCommand(*row) for row in rows]
