"""Private seat ownership, lobby races, receipts and resumable bot work."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

import pytest

from sway.bots import BotState, choose
from sway.engine import Card, Command, GameConfig, GameState, InvalidCommand, Transition
from sway.hosting.dispatcher import BotDispatcher
from sway.hosting.identity import AuthenticationError, IdentityCredentials, IdentityService
from sway.hosting.service import HostedService, TableView
from sway.hosting.storage import HostedStore
from sway.service import deserialize_game, serialize_game
from sway.storage import GameNotFound, StorageConflict, StoredGame


@pytest.fixture(autouse=True)
def deterministic_seed(monkeypatch: pytest.MonkeyPatch) -> None:
    def seed(_bits: int) -> int:
        return 2

    monkeypatch.setattr("sway.hosting.service.secrets.randbits", seed)


def account(service: HostedService, name: str) -> IdentityCredentials:
    identity = IdentityService(service.store)
    return identity.create_principal(identity.anonymous_session().token, name)


def setup(
    tmp_path: Path, controllers: tuple[str, ...] = ("human", "human")
) -> tuple[HostedService, list[IdentityCredentials], TableView]:
    service = HostedService(HostedStore(tmp_path / "hosted.sqlite3"))
    users = [account(service, "Alice")]
    table = service.create(users[0].session.token, controllers)
    for seat, controller in enumerate(controllers[1:], 1):
        if controller == "human":
            users.append(account(service, f"Player {seat}"))
            invite = service.invite(users[0].session.token, table.game_id, seat)
            table = service.join(users[-1].session.token, invite.invitation_id, invite.secret)
    return service, users, table


def start(service: HostedService, users: list[IdentityCredentials], table: TableView) -> TableView:
    for user in users:
        table = service.ready(user.session.token, table.game_id, table.lobby_revision)
    return service.start(users[0].session.token, table.game_id, table.lobby_revision)


def command(table: TableView) -> Command:
    assert table.view is not None and table.view.pending is not None
    return choose(table.view, table.view.pending, BotState("engine", table.revision)).command


def raw(
    service: HostedService, game_id: str
) -> tuple[GameState, tuple[BotState, ...], frozenset[int]]:
    with service.store.transaction() as conn:
        row = conn.execute("SELECT * FROM hosted_rooms WHERE game_id=?", (game_id,)).fetchone()
        assert row is not None
        record = deserialize_game(
            StoredGame(
                game_id,
                cast(int, row["revision"]),
                cast(str, row["snapshot"]),
                "{}",
                "common-ground",
                cast(str, row["status"]),
                "",
            )
        )
        return record.state, record.bots, record.human_seats


def test_lobbies_two_three_four_seats_and_readiness(tmp_path: Path) -> None:
    for count in (2, 3, 4):
        service, users, table = setup(tmp_path / str(count), ("human",) * count)
        host = users[0].session.token
        with pytest.raises(StorageConflict, match="ready"):
            service.start(host, table.game_id, table.lobby_revision)
        initial = table.lobby_revision
        table = start(service, users, table)
        assert table.status == "active"
        assert table.lobby_revision > initial
        assert all(seat.occupied for seat in table.seats)
        assert table.view is not None and table.view.player == 0
        assert "seed" not in json.dumps(asdict(table))
        for index, user in enumerate(users):
            private = service.view(user.session.token, table.game_id)
            assert private.seat == index and private.view is not None
            assert private.view.player == index
            if index != table.pending_player:
                assert private.view.pending is None


def test_membership_hides_unknown_and_other_tables(tmp_path: Path) -> None:
    service, users, table = setup(tmp_path)
    outsider = account(service, "Stranger").session.token
    for game_id in (table.game_id, "missing"):
        with pytest.raises(GameNotFound, match="Table unavailable"):
            service.view(outsider, game_id)
        with pytest.raises(GameNotFound):
            service.set_theme(outsider, game_id, "orbital", 0)
        with pytest.raises(GameNotFound):
            service.submit(outsider, game_id, "guess", Command("wrong", 0, ()))
    assert service.list_tables(outsider) == ()
    assert service.list_tables(users[1].session.token)[0].game_id == table.game_id
    with pytest.raises(GameNotFound):
        service.cancel(users[1].session.token, table.game_id)
    with pytest.raises(GameNotFound):
        service.create(service.identity.anonymous_session().token, ("human", "economy"))


def test_invites_single_use_reissued_revoked_expired_and_same_member_retry(tmp_path: Path) -> None:
    now = [100.0]
    service = HostedService(HostedStore(tmp_path / "hosted.sqlite3", clock=lambda: now[0]))
    host = account(service, "Alice").session.token
    bob = account(service, "Bob").session.token
    eve = account(service, "Eve").session.token
    table = service.create(host, ("human", "human", "human"))
    old = service.invite(host, table.game_id, 1)
    invitation = service.invite(host, table.game_id, 1)
    with pytest.raises(GameNotFound):
        service.join(bob, old.invitation_id, old.secret)
    with pytest.raises(GameNotFound):
        service.join(bob, invitation.invitation_id, "wrong")
    joined = service.join(bob, invitation.invitation_id, invitation.secret)
    assert service.join(bob, invitation.invitation_id, invitation.secret) == joined
    with pytest.raises(GameNotFound):
        service.join(eve, invitation.invitation_id, invitation.secret)
    other = service.invite(host, table.game_id, 2)
    with pytest.raises(StorageConflict, match="already"):
        service.join(bob, other.invitation_id, other.secret)
    service.revoke_invite(host, table.game_id, 2)
    with pytest.raises(GameNotFound):
        service.join(eve, other.invitation_id, other.secret)
    expiring = service.invite(host, table.game_id, 2)
    now[0] = expiring.expires_at
    with pytest.raises(GameNotFound):
        service.join(eve, expiring.invitation_id, expiring.secret)
    with service.store.transaction() as conn:
        stored = str(conn.execute("SELECT * FROM hosted_invitations").fetchall())
    assert invitation.secret not in stored
    assert invitation.secret not in repr(invitation)


def test_invite_concurrent_claim_has_one_winner_and_guest_rollback(tmp_path: Path) -> None:
    service = HostedService(HostedStore(tmp_path / "hosted.sqlite3"))
    host = account(service, "Alice").session.token
    table = service.create(host, ("human", "human"))
    invitation = service.invite(host, table.game_id, 1)
    tokens = [account(service, name).session.token for name in ("Bob", "Eve")]
    barrier = threading.Barrier(2)

    def claim(token: str) -> bool:
        barrier.wait()
        try:
            independent = HostedService(HostedStore(service.store.path))
            independent.join(token, invitation.invitation_id, invitation.secret)
        except GameNotFound:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, tokens)) == [False, True]
    anonymous = service.identity.anonymous_session()
    with service.store.transaction() as conn:
        before = conn.execute("SELECT count(*) FROM principals").fetchone()[0]
    with pytest.raises(GameNotFound):
        service.join_guest(anonymous.token, invitation.invitation_id, "wrong", "New guest")
    assert service.identity.authenticate(anonymous.token).principal_id is None
    with service.store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM principals").fetchone()[0] == before


def test_join_guest_and_remove_changes_readiness_and_authority(tmp_path: Path) -> None:
    service = HostedService(HostedStore(tmp_path / "hosted.sqlite3"))
    host = account(service, "Alice").session.token
    table = service.create(host, ("human", "human"))
    invitation = service.invite(host, table.game_id, 1)
    guest, table = service.join_guest(
        service.identity.anonymous_session().token,
        invitation.invitation_id,
        invitation.secret,
        "Bob",
    )
    table = service.ready(host, table.game_id, table.lobby_revision)
    table = service.ready(guest.session.token, table.game_id, table.lobby_revision)
    assert all(seat.ready for seat in table.seats)
    table = service.remove(host, table.game_id, 1, table.lobby_revision)
    assert not any(seat.ready for seat in table.seats)
    with pytest.raises(GameNotFound):
        service.view(guest.session.token, table.game_id)
    with pytest.raises(GameNotFound):
        service.join(guest.session.token, invitation.invitation_id, invitation.secret)
    with pytest.raises(ValueError):
        service.remove(host, table.game_id, 0, table.lobby_revision)
    table = service.configure(
        host,
        table.game_id,
        table.lobby_revision,
        ("human", "engine", "attack"),
        GameConfig().kingdom,
    )
    table = service.ready(host, table.game_id, table.lobby_revision)
    table = service.start(host, table.game_id, table.lobby_revision)
    with pytest.raises(StorageConflict):
        service.configure(
            host, table.game_id, table.lobby_revision, ("human", "human"), GameConfig().kingdom
        )
    with pytest.raises(StorageConflict):
        service.invite(host, table.game_id, 1)


def test_setup_edit_invalidates_ready_and_stale_lobby(tmp_path: Path) -> None:
    service, users, table = setup(tmp_path)
    host = users[0].session.token
    before = table.lobby_revision
    table = service.ready(host, table.game_id, before)
    with pytest.raises(StorageConflict):
        service.ready(users[1].session.token, table.game_id, before)
    with pytest.raises(StorageConflict, match="Remove"):
        service.configure(
            host, table.game_id, table.lobby_revision, ("human", "economy"), table.kingdom
        )
    table = service.configure(
        host, table.game_id, table.lobby_revision, ("human", "human", "economy"), table.kingdom
    )
    assert not any(seat.ready for seat in table.seats)
    table = service.cancel(host, table.game_id)
    assert table.status == "cancelled" and table.view is None
    assert service.cancel(host, table.game_id) == table


def test_receipt_retry_precedes_stale_and_pending_owner_checks(tmp_path: Path) -> None:
    service, users, table = setup(tmp_path)
    host = users[0].session.token
    table = start(service, users, table)
    cmd = command(table)
    accepted = service.submit(host, table.game_id, "request-1", cmd)
    assert accepted.accepted_revision == 1
    retry = service.submit(host, table.game_id, "request-1", cmd)
    assert retry == accepted
    with pytest.raises(StorageConflict, match="reused"):
        service.submit(host, table.game_id, "request-1", replace(cmd, selections=("invalid",)))
    with pytest.raises(StorageConflict):
        service.submit(host, table.game_id, "request-2", cmd)
    with pytest.raises(InvalidCommand, match="your decision"):
        service.submit(
            users[1].session.token, table.game_id, "wrong-owner", command(accepted.table)
        )
    service.cancel(host, table.game_id)
    assert service.submit(host, table.game_id, "request-1", cmd).table.status == "cancelled"
    with service.store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM hosted_commands").fetchone()[0] == 1


def test_two_tabs_and_same_request_race_commit_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sway.hosting.service as module

    service, users, table = setup(tmp_path)
    table = start(service, users, table)
    cmd = command(table)
    original = module.advance
    barrier = threading.Barrier(2)

    def racing_advance(state: GameState, command: Command) -> Transition:
        result = original(state, command)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(module, "advance", racing_advance)

    def submit(request_id: str) -> int:
        try:
            return service.submit(
                users[0].session.token, table.game_id, request_id, cmd
            ).accepted_revision
        except StorageConflict:
            return -1

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, ("one", "two"))) == [-1, 1]
    monkeypatch.setattr(module, "advance", original)
    table = service.view(users[0].session.token, table.game_id)
    cmd = command(table)
    monkeypatch.setattr(module, "advance", racing_advance)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(submit, ("same", "same"))) == [2, 2]


def test_session_recovery_during_compute_prevents_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sway.hosting.service as module

    service, users, table = setup(tmp_path)
    table = start(service, users, table)
    original = module.advance
    recovered: list[IdentityCredentials] = []

    def recovering_advance(state: GameState, command: Command) -> Transition:
        result = original(state, command)
        recovered.append(
            service.identity.recover(
                service.identity.anonymous_session().token, users[0].recovery_code
            )
        )
        return result

    monkeypatch.setattr(module, "advance", recovering_advance)
    with pytest.raises(AuthenticationError):
        service.submit(users[0].session.token, table.game_id, "revoked", command(table))
    current = service.view(recovered[0].session.token, table.game_id)
    assert current.revision == 0 and current.seat == 0
    with pytest.raises(AuthenticationError):
        service.view(users[0].session.token, table.game_id)


def test_cancel_during_compute_and_atomic_failed_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sway.hosting.service as module

    service, users, table = setup(tmp_path)
    table = start(service, users, table)
    host = users[0].session.token
    with service.store.transaction(write=True) as conn:
        conn.execute(
            "CREATE TRIGGER reject_snapshot BEFORE UPDATE OF snapshot ON hosted_rooms BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        service.submit(host, table.game_id, "rollback", command(table))
    with service.store.transaction(write=True) as conn:
        assert conn.execute("SELECT count(*) FROM hosted_commands").fetchone()[0] == 0
        conn.execute("DROP TRIGGER reject_snapshot")
    original = module.advance

    def cancelled_advance(state: GameState, command: Command) -> Transition:
        result = original(state, command)
        service.cancel(host, table.game_id)
        return result

    monkeypatch.setattr(module, "advance", cancelled_advance)
    with pytest.raises(StorageConflict):
        service.submit(host, table.game_id, "cancelled", command(table))
    current = service.view(host, table.game_id)
    assert current.revision == 0 and current.status == "cancelled"


def test_viewer_theme_uses_separate_version(tmp_path: Path) -> None:
    service, users, table = setup(tmp_path)
    table = start(service, users, table)
    before = service.view(users[1].session.token, table.game_id)
    changed = service.set_theme(users[0].session.token, table.game_id, "orbital", 0)
    assert changed.preference_version == 1 and changed.theme_id == "orbital"
    assert changed.revision == table.revision and changed.view == table.view
    assert service.view(users[1].session.token, table.game_id) == before
    with pytest.raises(StorageConflict):
        service.set_theme(users[0].session.token, table.game_id, "common-ground", 0)
    with pytest.raises(ValueError):
        service.set_theme(users[0].session.token, table.game_id, "../evil", 1)


def bot_turn(service: HostedService, token: str, game_id: str) -> None:
    for index in range(30):
        table = service.view(token, game_id)
        if table.pending_player != table.seat:
            return
        service.submit(token, game_id, f"human-{table.revision}-{index}", command(table))
    pytest.fail("Human turn failed to finish.")


def test_bot_failure_pauses_and_explicit_retry_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sway.hosting.service as module

    service, users, table = setup(tmp_path, ("human", "engine"))
    table = start(service, users, table)
    host = users[0].session.token
    bot_turn(service, host, table.game_id)
    assert service.pending_bot_games() == (table.game_id,)
    original = module.choose

    def fail(*_args: object) -> None:
        raise RuntimeError("sensitive internal details")

    monkeypatch.setattr(module, "choose", fail)
    assert not service.step_bots(table.game_id)
    paused = service.view(host, table.game_id)
    assert paused.bot_paused == "decision_failed"
    assert "sensitive" not in repr(paused)
    assert service.pending_bot_games() == ()
    assert not service.step_bots(table.game_id)
    service.retry_bots(host, table.game_id)
    monkeypatch.setattr(module, "choose", original)
    while service.step_bots(table.game_id):
        pass
    assert service.view(host, table.game_id).pending_player == 0


def test_bot_restart_preserves_random_state_and_dispatcher_recovers_unqueued_work(
    tmp_path: Path,
) -> None:
    service, users, table = setup(tmp_path, ("human", "engine", "attack"))
    table = start(service, users, table)
    host = users[0].session.token
    bot_turn(service, host, table.game_id)
    service.step_bots(table.game_id, max_steps=1)
    backup = tmp_path / "control.sqlite3"
    backup.touch(mode=0o600)
    with sqlite3.connect(service.store.path) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)
    control = HostedService(HostedStore(backup))
    while control.step_bots(table.game_id):
        pass
    resumed = HostedService(HostedStore(service.store.path))
    dispatcher = BotDispatcher(resumed, scan_seconds=0.02)
    dispatcher.start()
    dispatcher.start()
    try:
        deadline = time.monotonic() + 5
        while resumed.pending_bot_games() and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        dispatcher.stop()
    assert raw(resumed, table.game_id) == raw(control, table.game_id)
    assert resumed.view(host, table.game_id).pending_player == 0


def test_nested_human_reaction_authorizes_target_and_restarts_privately(tmp_path: Path) -> None:
    from sway.engine import advance

    service, users, table = setup(tmp_path, ("human", "human", "human"))
    table = start(service, users, table)
    state, bots, humans = raw(service, table.game_id)
    state.players[0].hand = [Card("c100", "k14")]
    state.players[1].hand = [Card("c101", "k16")]
    # Ask the engine to rebuild the action menu after a test fixture hand change.
    from sway.engine.models import Decision, Effect, Option

    state.pending = Decision(
        "fixture-attack",
        0,
        "menu",
        "action",
        (Option("c100", "k14", "c100"), Option("end-actions")),
        1,
        1,
    )
    state.next_instance_id = 102
    state.pending_effect = Effect("action", 0)
    result = advance(state, Command("fixture-attack", state.revision, ("c100",)))
    with service.store.transaction(write=True) as conn:
        conn.execute(
            "UPDATE hosted_rooms SET snapshot=?,revision=? WHERE game_id=?",
            (serialize_game(result.state, bots, humans), result.state.revision, table.game_id),
        )
    assert result.state.pending is not None and result.state.pending.player == 1
    resumed = HostedService(HostedStore(service.store.path))
    host = resumed.view(users[0].session.token, table.game_id)
    target = resumed.view(users[1].session.token, table.game_id)
    other = resumed.view(users[2].session.token, table.game_id)
    assert host.view is not None and host.view.pending is None
    assert other.view is not None and other.view.pending is None
    assert target.view is not None and target.view.pending is not None
    assert target.view.active_player == 0 and target.pending_player == 1
    assert "c101" not in json.dumps(asdict(other))
    with pytest.raises(InvalidCommand):
        resumed.submit(users[0].session.token, table.game_id, "attack-owner", command(target))
    resumed.submit(users[1].session.token, table.game_id, "reaction-owner", command(target))


def test_random_bot_start_is_durable_without_human_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def seed(_bits: int) -> int:
        return 0

    monkeypatch.setattr("sway.hosting.service.secrets.randbits", seed)
    service, users, table = setup(tmp_path, ("human", "engine", "attack"))
    table = start(service, users, table)
    assert table.pending_player == 1
    assert service.pending_bot_games() == (table.game_id,)
    before = table.revision
    service.step_bots(table.game_id, max_steps=1)
    assert service.view(users[0].session.token, table.game_id).revision == before + 1


def test_unready_during_start_compute_prevents_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sway.hosting.service as module

    service, users, table = setup(tmp_path)
    for user in users:
        table = service.ready(user.session.token, table.game_id, table.lobby_revision)
    original = module.new_game

    def unready(config: GameConfig, seed: int) -> GameState:
        state = original(config, seed)
        service.ready(users[1].session.token, table.game_id, table.lobby_revision, False)
        return state

    monkeypatch.setattr(module, "new_game", unready)
    with pytest.raises(StorageConflict):
        service.start(users[0].session.token, table.game_id, table.lobby_revision)
    current = service.view(users[0].session.token, table.game_id)
    assert current.status == "lobby" and current.view is None


def test_concurrent_bot_jobs_do_not_double_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sway.hosting.service as module

    service, users, table = setup(tmp_path, ("human", "engine"))
    table = start(service, users, table)
    bot_turn(service, users[0].session.token, table.game_id)
    before = service.view(users[0].session.token, table.game_id).revision
    barrier = threading.Barrier(2)

    # Synchronize the engine boundary; both jobs compute the same saved decision.
    original_advance = module.advance

    def racing_advance(state: GameState, cmd: Command) -> Transition:
        result = original_advance(state, cmd)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(module, "advance", racing_advance)

    def job(_index: int) -> bool:
        return service.step_bots(table.game_id, max_steps=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(job, range(2)))
    assert service.view(users[0].session.token, table.game_id).revision == before + 1


def test_validation_and_cancelled_bot_work(tmp_path: Path) -> None:
    service, users, table = setup(tmp_path)
    token = users[0].session.token
    for controllers in (("human",), ("engine", "human"), ("human", "unknown")):
        with pytest.raises(ValueError):
            service.create(token, controllers)
    with pytest.raises(ValueError):
        service.create(token, ("human", "human"), ("k01",))
    with pytest.raises(ValueError):
        service.submit(token, table.game_id, "invalid request", Command("d0", 0, ()))
    for steps, budget in ((0, 0.1), (9, 0.1), (1, 0), (1, 0.2)):
        with pytest.raises(ValueError):
            service.step_bots(table.game_id, steps, budget)
    with pytest.raises(ValueError):
        service.pending_bot_games(0)
    with pytest.raises(ValueError):
        BotDispatcher(service, scan_seconds=0)
    service.cancel(token, table.game_id)
    assert service.step_bots(table.game_id) is False
    with pytest.raises(StorageConflict):
        service.retry_bots(token, table.game_id)
