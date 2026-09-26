"""Synchronous transaction contract shared by hosted persistence adapters.

Callbacks must finish synchronously, must not escape their session, and must not
perform network I/O. A write either commits all effects or rolls them all back;
a read sees one consistent snapshot. This maps to SQLite transactions locally
and Durable Object transactionSync without emulating a native connection.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

type SqlValue = str | int | float | bytes | None
type SqlRow = Mapping[str, SqlValue]


@dataclass(frozen=True)
class SqlResult:
    rows: tuple[SqlRow, ...] = ()
    rows_written: int = 0

    def one(self) -> SqlRow | None:
        return self.rows[0] if self.rows else None

    def all(self) -> list[SqlRow]:
        return list(self.rows)


class SqlSession(Protocol):
    def execute(self, sql: str, parameters: tuple[SqlValue, ...] = ()) -> SqlResult: ...


class StateStore(Protocol):
    @property
    def clock(self) -> Callable[[], float]: ...

    def read[T](self, operation: Callable[[SqlSession], T]) -> T: ...

    def write[T](self, operation: Callable[[SqlSession], T]) -> T: ...
