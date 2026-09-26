"""Application contracts use synchronous callbacks, not native connection APIs."""

from collections.abc import Callable
from pathlib import Path

import pytest

import sway.hosting.service as service_module
from sway.bots import BotState, choose
from sway.engine import Command, GameState, Transition
from sway.hosting.schema import initialize_identity
from sway.hosting.service import HostedService
from sway.hosting.state import SqlSession
from sway.hosting.storage import HostedStore
from sway.storage import GameNotFound, SaveFormatError


class CallbackStore:
    """Expose only the portable contract and reject nested transactions."""

    def __init__(self, backing: HostedStore) -> None:
        self._backing = backing
        self.clock = backing.clock
        self.active = False
        self.writes = 0

    def read[T](self, operation: Callable[[SqlSession], T]) -> T:
        assert not self.active
        self.active = True
        try:
            return self._backing.read(operation)
        finally:
            self.active = False

    def write[T](self, operation: Callable[[SqlSession], T]) -> T:
        assert not self.active
        self.writes += 1
        self.active = True
        try:
            return self._backing.write(operation)
        finally:
            self.active = False


def test_guest_join_composes_one_callback_and_rolls_back_every_effect(tmp_path: Path) -> None:
    store = CallbackStore(HostedStore(tmp_path / "hosted.sqlite3"))
    service = HostedService(store)
    host = service.identity.create_principal(service.identity.anonymous_session().token, "Host")
    table = service.create(host.session.token, ("human", "human"))
    invitation = service.invite(host.session.token, table.game_id, 1)
    guest = service.identity.anonymous_session()
    before = store.writes
    with pytest.raises(GameNotFound):
        service.join_guest(guest.token, invitation.invitation_id, "wrong-secret", "Guest")
    assert store.writes == before + 1
    assert service.identity.authenticate(guest.token).principal_id is None
    principals = store.read(lambda sql: sql.execute("SELECT principal_id FROM principals").all())
    assert len(principals) == 1
    before = store.writes
    credentials, joined = service.join_guest(
        guest.token, invitation.invitation_id, invitation.secret, "Guest"
    )
    assert store.writes == before + 1
    assert joined.seat == 1
    assert service.identity.authenticate(credentials.session.token).principal_id is not None


def test_engine_computation_occurs_outside_portable_transactions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = CallbackStore(HostedStore(tmp_path / "hosted.sqlite3"))
    service = HostedService(store)
    host = service.identity.create_principal(service.identity.anonymous_session().token, "Host")
    table = service.create(host.session.token, ("human", "engine"))
    table = service.ready(host.session.token, table.game_id, table.lobby_revision)
    table = service.start(host.session.token, table.game_id, table.lobby_revision)
    original = service_module.advance
    computations = 0

    def checked_advance(state: GameState, command: Command) -> Transition:
        nonlocal computations
        assert not store.active
        computations += 1
        return original(state, command)

    monkeypatch.setattr(service_module, "advance", checked_advance)
    # Cover human moves and a bot batch without depending on which seat starts.
    for index in range(100):
        table = service.view(host.session.token, table.game_id)
        assert table.view is not None
        if table.view.pending is None:
            before = computations
            service.step_bots(table.game_id)
            assert computations > before
            break
        command = choose(table.view, table.view.pending, BotState("engine", index)).command
        result = service.submit(host.session.token, table.game_id, f"move-{index}", command)
        assert result.accepted_revision == table.revision + 1
        assert service.submit(host.session.token, table.game_id, f"move-{index}", command) == result
    else:
        pytest.fail("Human choices did not reach a bot decision within the bound.")


def test_results_remain_values_after_callback_closes_connection(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.sqlite3")
    result = store.read(lambda sql: sql.execute("SELECT version FROM hosting_schema"))
    assert result.one() == {"version": 1}
    assert result.all() == [{"version": 1}]
    missing = store.read(lambda sql: sql.execute("SELECT 1 WHERE 0"))
    assert missing.one() is None and missing.all() == []
    changed = store.write(
        lambda sql: sql.execute(
            "UPDATE hosting_schema SET version=version WHERE component=?", ("identity",)
        )
    )
    assert changed.rows_written == 1
    unchanged = store.write(
        lambda sql: sql.execute(
            "UPDATE hosting_schema SET version=version WHERE component=?", ("missing",)
        )
    )
    assert unchanged.rows_written == 0


def test_shared_schema_is_idempotent_and_rejects_unknown_version(tmp_path: Path) -> None:
    store = HostedStore(tmp_path / "hosted.sqlite3")
    store.write(initialize_identity)
    store.write(lambda sql: sql.execute("UPDATE hosting_schema SET version=99"))
    with pytest.raises(SaveFormatError, match="schema version"):
        store.write(initialize_identity)
    assert store.read(lambda sql: sql.execute("SELECT version FROM hosting_schema").one()) == {
        "version": 99
    }
