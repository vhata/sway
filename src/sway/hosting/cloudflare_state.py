"""Durable Object SQL adapter; the application never sees JavaScript bindings."""

import time
from collections.abc import Callable
from typing import Protocol

from sway.hosting.state import SqlResult, SqlRow, SqlSession, SqlValue


class SqlCursor(Protocol):
    def toArray(self) -> list[SqlRow]: ...


class SqlBinding(Protocol):
    def exec(self, statement: str, *parameters: SqlValue) -> SqlCursor: ...


class DurableStorage(Protocol):
    @property
    def sql(self) -> SqlBinding: ...
    def transactionSync[T](self, operation: Callable[[], T]) -> T: ...


class DurableSession:
    def __init__(self, sql: SqlBinding, *, writable: bool) -> None:
        self.sql = sql
        self.writable = writable
        self.active = True

    def execute(self, sql: str, parameters: tuple[SqlValue, ...] = ()) -> SqlResult:
        if not self.active:
            raise RuntimeError("A transaction session cannot escape its callback.")
        if not self.writable and not sql.lstrip().upper().startswith("SELECT "):
            raise ValueError("A read transaction cannot modify state.")
        rows = tuple(self.sql.exec(sql, *parameters).toArray())
        changes = self.sql.exec("SELECT changes() AS count").toArray()[0]["count"]
        return SqlResult(rows, int(changes) if isinstance(changes, (int, float)) else 0)


class DurableStateStore:
    def __init__(self, storage: DurableStorage, *, clock: Callable[[], float] = time.time) -> None:
        self.storage = storage
        self.clock = clock

    def _run[T](self, operation: Callable[[SqlSession], T], *, write: bool) -> T:
        # Preserve the original Python exception across the JavaScript FFI boundary.
        # Cloudflare still receives the exception, so it rolls back before we re-raise.
        failure: list[BaseException] = []
        result: list[T] = []

        def transaction() -> None:
            session = DurableSession(self.storage.sql, writable=write)
            try:
                result.append(operation(session))
            except BaseException as exc:
                failure.append(exc)
                raise
            finally:
                session.active = False

        try:
            self.storage.transactionSync(transaction)
        except BaseException:
            if failure:
                raise failure[0] from None
            raise
        return result[0]

    def read[T](self, operation: Callable[[SqlSession], T]) -> T:
        return self._run(operation, write=False)

    def write[T](self, operation: Callable[[SqlSession], T]) -> T:
        return self._run(operation, write=True)
