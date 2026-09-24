"""Backup and restore cover credentials and game state as one SQLite snapshot."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from sway.hosting.backup import APPLICATION_ID, copy_database, main


def create_database(path: Path) -> sqlite3.Connection:
    path.touch(mode=0o600)
    connection = sqlite3.connect(path)
    _ = connection.execute("PRAGMA journal_mode=WAL").fetchone()
    connection.executescript(f"""
        PRAGMA application_id = {APPLICATION_ID};
        PRAGMA user_version = 1;
        PRAGMA foreign_keys = ON;
        CREATE TABLE hosting_schema(component TEXT PRIMARY KEY, version INTEGER);
        INSERT INTO hosting_schema VALUES ('identity', 1);
        CREATE TABLE principal(id TEXT PRIMARY KEY, recovery_hash TEXT);
        CREATE TABLE session(token_hash TEXT PRIMARY KEY, principal_id TEXT REFERENCES principal(id));
        CREATE TABLE game(id TEXT PRIMARY KEY, snapshot TEXT);
        CREATE TABLE membership(principal_id TEXT REFERENCES principal(id), game_id TEXT REFERENCES game(id));
        INSERT INTO principal VALUES ('alice', 'hashed-recovery');
        INSERT INTO session VALUES ('hashed-session', 'alice');
        INSERT INTO game VALUES ('table', 'private-game-state');
        INSERT INTO membership VALUES ('alice', 'table');
    """)
    return connection


def test_backup_live_wal_then_restore_preserves_every_table(tmp_path: Path) -> None:
    original, backup, restored = (
        tmp_path / name for name in ("live.sqlite3", "backup.sqlite3", "restore.sqlite3")
    )
    with closing(create_database(original)) as live:
        assert Path(str(original) + "-wal").exists()
        _ = copy_database(original, backup)
        # Prove committed state survived independently of later source mutations.
        _ = live.execute("UPDATE game SET snapshot = 'next-state'")
        live.commit()
        _ = copy_database(backup, restored)
        with closing(sqlite3.connect(restored)) as recovered:
            assert recovered.execute("SELECT * FROM principal").fetchall() == [
                ("alice", "hashed-recovery")
            ]
            assert recovered.execute("SELECT * FROM session").fetchall() == [
                ("hashed-session", "alice")
            ]
            assert recovered.execute("SELECT * FROM game").fetchall() == [
                ("table", "private-game-state")
            ]
            assert recovered.execute("SELECT * FROM membership").fetchall() == [("alice", "table")]
    assert backup.stat().st_mode & 0o777 == 0o600
    assert restored.stat().st_mode & 0o777 == 0o600
    assert not Path(str(backup) + "-wal").exists()


def test_refuse_overwrite_and_source_alias(tmp_path: Path) -> None:
    original = tmp_path / "live.sqlite3"
    with closing(create_database(original)):
        before = original.read_bytes()
        with pytest.raises(FileExistsError):
            _ = copy_database(original, original)
        alias = tmp_path / "alias"
        alias.symlink_to(original)
        with pytest.raises(FileExistsError):
            _ = copy_database(original, alias)
        assert original.read_bytes() == before


@pytest.mark.parametrize(
    "damage",
    [
        "PRAGMA application_id=0",
        "PRAGMA user_version=99",
        "UPDATE hosting_schema SET version=99",
        "INSERT INTO hosting_schema VALUES ('multiplayer', 99)",
        "INSERT INTO hosting_schema VALUES ('unknown', 1)",
        "PRAGMA foreign_keys=OFF; INSERT INTO membership VALUES ('unknown','table')",
    ],
)
def test_reject_bad_format_and_broken_relations(tmp_path: Path, damage: str) -> None:
    original, backup = tmp_path / "live.sqlite3", tmp_path / "copy.sqlite3"
    with closing(create_database(original)) as live:
        live.executescript(damage)
        with pytest.raises(ValueError):
            _ = copy_database(original, backup)
    assert not backup.exists()
    assert original.exists()


def test_reject_permissive_files_and_destinations(tmp_path: Path) -> None:
    original = tmp_path / "live.sqlite3"
    with closing(create_database(original)):
        original.chmod(0o644)
        with pytest.raises(ValueError, match="Source"):
            _ = copy_database(original, tmp_path / "backup")
        original.chmod(0o600)
        public = tmp_path / "public"
        public.mkdir(mode=0o755)
        public.chmod(0o755)
        with pytest.raises(ValueError, match="Destination"):
            _ = copy_database(original, public / "backup")


def test_copy_timeout_cleans_destination(tmp_path: Path) -> None:
    original, backup = tmp_path / "live.sqlite3", tmp_path / "backup"
    with closing(create_database(original)):
        with pytest.raises(TimeoutError):
            _ = copy_database(original, backup, timeout=1e-12)
        assert not backup.exists()


def test_cli_backup_and_restore(tmp_path: Path) -> None:
    original, backup, restored = (
        tmp_path / name for name in ("live.sqlite3", "backup.sqlite3", "restore.sqlite3")
    )
    with closing(create_database(original)):
        assert main(["backup", str(original), str(backup)]) == 0
    assert main(["restore", str(backup), str(restored)]) == 0
    with pytest.raises(SystemExit) as failure:
        _ = main(["restore", str(backup), str(restored)])
    assert failure.value.code == 1


@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm"])
@pytest.mark.parametrize("symlink", [False, True])
def test_existing_sidecars_are_preserved(tmp_path: Path, suffix: str, symlink: bool) -> None:
    original, backup = tmp_path / "live.sqlite3", tmp_path / "backup.sqlite3"
    sidecar = Path(str(backup) + suffix)
    if symlink:
        sidecar.symlink_to(tmp_path / "missing-target")
    else:
        sidecar.write_text("preexisting unrelated file")
    with closing(create_database(original)):
        with pytest.raises(FileExistsError, match="sidecar"):
            _ = copy_database(original, backup)
    assert not backup.exists()
    if symlink:
        assert sidecar.is_symlink()
    else:
        assert sidecar.read_text() == "preexisting unrelated file"


def test_restored_multiplayer_database_keeps_sessions_seats_and_command_receipts(
    tmp_path: Path,
) -> None:
    from sway.bots import BotState, choose
    from sway.hosting.service import HostedService
    from sway.hosting.storage import HostedStore

    service = HostedService(HostedStore(tmp_path / "hosted.sqlite3"))
    identity = service.identity
    alice = identity.create_principal(identity.anonymous_session().token, "Alice")
    bob = identity.create_principal(identity.anonymous_session().token, "Bob")
    table = service.create(alice.session.token, ("human", "human"))
    invitation = service.invite(alice.session.token, table.game_id, 1)
    table = service.join(bob.session.token, invitation.invitation_id, invitation.secret)
    for credentials in (alice, bob):
        table = service.ready(credentials.session.token, table.game_id, table.lobby_revision)
    table = service.start(alice.session.token, table.game_id, table.lobby_revision)
    assert table.pending_player is not None
    actor = (alice, bob)[table.pending_player]
    table = service.view(actor.session.token, table.game_id)
    assert table.view is not None and table.view.pending is not None
    command = choose(table.view, table.view.pending, BotState("engine", 7)).command
    accepted = service.submit(actor.session.token, table.game_id, "first-choice", command)
    bob_view = service.view(bob.session.token, table.game_id)
    backup, restored = tmp_path / "backup.sqlite3", tmp_path / "restored.sqlite3"
    _ = copy_database(service.store.path, backup)
    _ = copy_database(backup, restored)
    recovered = HostedService(HostedStore(restored))
    assert recovered.identity.authenticate(alice.session.token) == alice.session.session
    assert recovered.view(bob.session.token, table.game_id) == bob_view
    retry = recovered.submit(actor.session.token, table.game_id, "first-choice", command)
    assert retry == accepted
    new = recovered.identity.recover(
        recovered.identity.anonymous_session().token, bob.recovery_code
    )
    assert recovered.view(new.session.token, table.game_id).seat == 1
