"""Storage contract tests reusable by future adapters."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from sway.storage import GameNotFound, SaveFormatError, SQLiteStore, StorageConflict, Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return SQLiteStore(tmp_path / "saves.sqlite3")


def test_create_list_reload_and_theme_preserve_state(store: Store) -> None:
    created = store.create("a", '{"version":1}', '{"name":"test"}', "common-ground")
    assert store.load("a") == created
    assert store.list_games() == [created]
    themed = store.set_theme("a", "orbital")
    assert themed.theme_id == "orbital"
    assert themed.snapshot == created.snapshot
    assert themed.revision == created.revision
    assert store.history("a") == []


def test_transition_is_atomic_and_repeat_is_idempotent(store: Store) -> None:
    store.create("a", "{}", "{}", "common-ground")
    first = store.commit("a", 0, "decision-1", '{"x":1}', '{"pick":"one"}', "[]")
    assert first.revision == 1
    assert store.history("a")[0].revision == 1
    repeated = store.commit("a", 0, "decision-1", '{"x":2}', '{"pick":"one"}', "[]")
    assert repeated == first
    assert len(store.history("a")) == 1
    with pytest.raises(StorageConflict):
        store.commit("a", 0, "decision-1", "{}", '{"pick":"two"}', "[]")
    with pytest.raises(StorageConflict):
        store.commit("a", 0, "decision-2", "{}", "{}", "[]")
    assert store.load("a") == first


def test_multiple_connections_cannot_overwrite_each_other(tmp_path: Path) -> None:
    path = tmp_path / "saves.sqlite3"
    first = SQLiteStore(path)
    second = SQLiteStore(path)
    first.create("a", "{}", "{}", "common-ground")

    def attempt(store: Store, command: str) -> bool:
        try:
            store.commit("a", 0, command, "{}", "{}", "[]")
        except StorageConflict:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(attempt, first, "one")
        two = pool.submit(attempt, second, "two")
        assert sorted([one.result(), two.result()]) == [False, True]
    assert first.load("a").revision == 1
    assert len(first.history("a")) == 1


def test_failed_transaction_rolls_back_snapshot_and_history(tmp_path: Path) -> None:
    path = tmp_path / "saves.sqlite3"
    store = SQLiteStore(path)
    before = store.create("a", "{}", "{}", "common-ground")
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TRIGGER fail_save BEFORE UPDATE ON games "
            "BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="simulated"):
        store.commit("a", 0, "one", '{"new":true}', "{}", "[]")
    assert SQLiteStore(path).load("a") == before
    assert store.history("a") == []


def test_invalid_save_preserves_original(store: Store) -> None:
    before = store.create("a", "{}", "{}", "common-ground")
    for bad in ("{", "[]", "null", "3"):
        with pytest.raises(SaveFormatError):
            store.commit("a", 0, "one", bad, "{}", "[]")
    with pytest.raises(SaveFormatError):
        store.commit("a", 0, "one", "{}", "{}", "{}")
    assert store.load("a") == before
    assert store.history("a") == []


def test_unknown_database_version_is_not_modified(tmp_path: Path) -> None:
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA user_version = 999")
    with pytest.raises(SaveFormatError, match="999"):
        SQLiteStore(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone() == (999,)


def test_missing_and_duplicate_games(store: Store) -> None:
    with pytest.raises(GameNotFound):
        store.load("missing")
    with pytest.raises(GameNotFound):
        store.history("missing")
    with pytest.raises(GameNotFound):
        store.set_theme("missing", "common-ground")
    store.create("a", "{}", "{}", "common-ground")
    with pytest.raises(StorageConflict):
        store.create("a", "{}", "{}", "common-ground")
