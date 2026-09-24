"""Credential lifecycle and independent-connection transactional contracts."""

from __future__ import annotations

import multiprocessing
import sqlite3
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from sway.hosting.identity import (
    ANONYMOUS_SECONDS,
    SESSION_SECONDS,
    AuthenticationError,
    IdentityCredentials,
    IdentityService,
    hash_secret,
)
from sway.hosting.storage import HostedStore
from sway.storage import SaveFormatError, SQLiteStore


@dataclass
class Clock:
    now: float = 1_000_000

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def identity(tmp_path: Path) -> IdentityService:
    return IdentityService(HostedStore(tmp_path / "hosted.sqlite3", clock=Clock()))


def guest(identity: IdentityService, name: str = "Alice") -> IdentityCredentials:
    return identity.create_principal(identity.anonymous_session().token, name)


def test_explicit_principal_creation_consumes_anonymous_session(identity: IdentityService) -> None:
    anonymous = identity.anonymous_session()
    assert anonymous.session.principal_id is None
    assert identity.check_csrf(anonymous.token, anonymous.session.csrf_token) == anonymous.session
    credentials = identity.create_principal(anonymous.token, " Alice ")
    assert credentials.session.session.principal_id is not None
    assert credentials.session.token != anonymous.token
    assert credentials.session.session.csrf_token != anonymous.session.csrf_token
    with pytest.raises(AuthenticationError):
        identity.authenticate(anonymous.token)
    with identity.store.transaction() as conn:
        assert conn.execute("SELECT display_name FROM principals").fetchone()[0] == "Alice"


def test_secrets_are_hash_only_and_not_repr(identity: IdentityService) -> None:
    credentials = guest(identity)
    secrets = (
        credentials.session.token,
        credentials.recovery_code,
        credentials.session.session.csrf_token,
    )
    for secret in secrets:
        assert len(secret) >= 43
        assert secret not in repr(credentials)
    with identity.store.transaction() as conn:
        data = "\n".join(conn.iterdump())
        assert all(secret not in data for secret in secrets)
        assert hash_secret(credentials.session.token) in data
        assert hash_secret(credentials.recovery_code) in data
    assert identity.store.path.stat().st_mode & 0o777 == 0o600


def test_sessions_expire_at_exact_fixed_boundary(identity: IdentityService) -> None:
    clock = cast(Clock, identity.store.clock)
    anonymous = identity.anonymous_session()
    clock.now += ANONYMOUS_SECONDS - 1
    identity.authenticate(anonymous.token)
    clock.now += 1
    with pytest.raises(AuthenticationError):
        identity.authenticate(anonymous.token)
    credentials = guest(identity)
    clock.now += SESSION_SECONDS - 1
    identity.authenticate(credentials.session.token)
    clock.now += 1
    with pytest.raises(AuthenticationError):
        identity.authenticate(credentials.session.token)


def test_csrf_is_session_bound_and_rejects_arbitrary_input(identity: IdentityService) -> None:
    first = identity.anonymous_session()
    second = identity.anonymous_session()
    for csrf in ("", "雪", second.session.csrf_token):
        with pytest.raises(AuthenticationError):
            identity.check_csrf(first.token, csrf)
    for token in ("", "x" * 129, "unknown"):
        with pytest.raises(AuthenticationError):
            identity.authenticate(token)


def test_recovery_rotates_code_and_revokes_all_existing_sessions(identity: IdentityService) -> None:
    old = guest(identity)
    unrelated = guest(identity, "Bob")
    # Model another browser session belonging to this principal.
    with identity.store.transaction(write=True) as conn:
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
            (
                "second",
                hash_secret("second-browser"),
                old.session.session.principal_id,
                0,
                9_999_999,
            ),
        )
    anonymous = identity.anonymous_session()
    new = identity.recover(anonymous.token, old.recovery_code)
    assert new.session.session.principal_id == old.session.session.principal_id
    assert new.recovery_code != old.recovery_code
    assert new.session.token != old.session.token
    for token in (old.session.token, "second-browser", anonymous.token):
        with pytest.raises(AuthenticationError):
            identity.authenticate(token)
    identity.authenticate(unrelated.session.token)
    with pytest.raises(AuthenticationError):
        identity.recover(identity.anonymous_session().token, old.recovery_code)
    again = identity.recover(identity.anonymous_session().token, new.recovery_code)
    assert again.session.session.principal_id == old.session.session.principal_id


def test_failed_recovery_preserves_both_sessions_and_recovery(identity: IdentityService) -> None:
    old = guest(identity)
    anonymous = identity.anonymous_session()
    for bad in ("", "invalid", "x" * 129):
        with pytest.raises(AuthenticationError):
            identity.recover(anonymous.token, bad)
    identity.authenticate(old.session.token)
    identity.authenticate(anonymous.token)
    identity.recover(anonymous.token, old.recovery_code)


@pytest.mark.parametrize("name", ["", "  ", "x" * 81, "hi\nthere", "hi\x00there"])
def test_invalid_names_leave_anonymous_session_usable(identity: IdentityService, name: str) -> None:
    anonymous = identity.anonymous_session()
    with pytest.raises(ValueError):
        identity.create_principal(anonymous.token, name)
    identity.authenticate(anonymous.token)
    with identity.store.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM principals").fetchone()[0] == 0


def test_authenticated_session_cannot_create_or_restore_another_principal(
    identity: IdentityService,
) -> None:
    credentials = guest(identity)
    with pytest.raises(AuthenticationError):
        identity.create_principal(credentials.session.token, "other")
    with pytest.raises(AuthenticationError):
        identity.recover(credentials.session.token, credentials.recovery_code)
    identity.authenticate(credentials.session.token)


def test_revocation_is_per_session_or_principal(identity: IdentityService) -> None:
    first = guest(identity)
    second = guest(identity)
    identity.revoke_session(first.session.token)
    identity.revoke_session(first.session.token)
    with pytest.raises(AuthenticationError):
        identity.authenticate(first.session.token)
    identity.authenticate(second.session.token)
    identity.revoke_all(second.session.token)
    with pytest.raises(AuthenticationError):
        identity.authenticate(second.session.token)
    anonymous = identity.anonymous_session()
    identity.revoke_all(anonymous.token)
    with pytest.raises(AuthenticationError):
        identity.authenticate(anonymous.token)


def test_create_and_recovery_compose_with_caller_rollback(identity: IdentityService) -> None:
    anonymous = identity.anonymous_session()
    issued: IdentityCredentials | None = None
    with pytest.raises(RuntimeError), identity.store.transaction(write=True) as conn:
        issued = identity.create_principal(anonymous.token, "Alice", conn=conn)
        identity.authenticate(issued.session.token, conn=conn)
        raise RuntimeError("joining failed")
    identity.authenticate(anonymous.token)
    assert issued is not None
    with pytest.raises(AuthenticationError):
        identity.authenticate(issued.session.token)
    old = guest(identity)
    with pytest.raises(RuntimeError), identity.store.transaction(write=True) as conn:
        identity.recover(anonymous.token, old.recovery_code, conn=conn)
        raise RuntimeError("response preparation failed")
    identity.authenticate(old.session.token)
    identity.recover(anonymous.token, old.recovery_code)


def test_concurrent_creation_has_one_winner(identity: IdentityService) -> None:
    token = identity.anonymous_session().token

    def create() -> bool:
        try:
            identity.create_principal(token, "Alice")
            return True
        except AuthenticationError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(create) for _ in range(2)]
        assert sorted(future.result(timeout=10) for future in futures) == [False, True]
    with identity.store.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM principals").fetchone()[0] == 1


def _recover_process(path: Path, token: str, code: str) -> bool:
    identity = IdentityService(HostedStore(path, clock=Clock()))
    try:
        identity.recover(token, code)
        return True
    except AuthenticationError:
        return False


def test_recovery_has_one_winner_across_processes(identity: IdentityService) -> None:
    credentials = guest(identity)
    tokens = [identity.anonymous_session().token for _ in range(2)]
    with ProcessPoolExecutor(
        max_workers=2, mp_context=multiprocessing.get_context("spawn")
    ) as executor:
        futures = [
            executor.submit(_recover_process, identity.store.path, token, credentials.recovery_code)
            for token in tokens
        ]
        assert sorted(future.result(timeout=20) for future in futures) == [False, True]
    with identity.store.transaction() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM sessions WHERE principal_id IS NOT NULL").fetchone()[
                0
            ]
            == 1
        )


def test_reopen_preserves_authentication_and_recovery(identity: IdentityService) -> None:
    original = guest(identity)
    reopened = IdentityService(HostedStore(identity.store.path, clock=Clock()))
    assert reopened.authenticate(original.session.token) == original.session.session
    restored = reopened.recover(reopened.anonymous_session().token, original.recovery_code)
    assert restored.session.session.principal_id == original.session.session.principal_id


def test_read_transactions_reject_writes(identity: IdentityService) -> None:
    with pytest.raises(sqlite3.OperationalError), identity.store.transaction() as conn:
        conn.execute("DELETE FROM principals")


def test_unsupported_and_local_databases_are_preserved(tmp_path: Path) -> None:
    local_path = tmp_path / "local.sqlite3"
    SQLiteStore(local_path)
    before = local_path.read_bytes()
    with pytest.raises(SaveFormatError, match="local saves are separate"):
        HostedStore(local_path)
    assert local_path.read_bytes() == before
    hosted = HostedStore(tmp_path / "hosted.sqlite3")
    with hosted.transaction(write=True) as conn:
        conn.execute("PRAGMA user_version = 99")
    before = hosted.path.read_bytes()
    with pytest.raises(SaveFormatError, match="Unsupported"):
        HostedStore(hosted.path)
    assert hosted.path.read_bytes() == before


def test_component_schema_mismatch_rejected(identity: IdentityService) -> None:
    with identity.store.transaction(write=True) as conn:
        conn.execute("UPDATE hosting_schema SET version=99 WHERE component='identity'")
    with pytest.raises(SaveFormatError, match="identity schema"):
        HostedStore(identity.store.path)


def test_read_transaction_sees_consistent_snapshot(identity: IdentityService) -> None:
    credentials = guest(identity)
    principal_id = credentials.session.session.principal_id
    with identity.store.transaction(write=True) as writer:
        with identity.store.transaction() as reader:
            before = reader.execute(
                "SELECT display_name FROM principals WHERE principal_id=?", (principal_id,)
            ).fetchone()[0]
            writer.execute(
                "UPDATE principals SET display_name='Changed' WHERE principal_id=?", (principal_id,)
            )
            assert (
                reader.execute(
                    "SELECT display_name FROM principals WHERE principal_id=?", (principal_id,)
                ).fetchone()[0]
                == before
            )
    with identity.store.transaction() as reader:
        assert (
            reader.execute(
                "SELECT display_name FROM principals WHERE principal_id=?", (principal_id,)
            ).fetchone()[0]
            == "Changed"
        )
