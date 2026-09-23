"""Human-controller authorization and save compatibility across arbitrary seats."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import cast

import pytest

from sway.bots import BotState, choose
from sway.engine import (
    Card,
    Command,
    Decision,
    Effect,
    GameConfig,
    InvalidCommand,
    Option,
    new_game,
    state_to_json,
)
from sway.service import GameRecord, GameService
from sway.storage import SaveFormatError, SQLiteStore, StorageConflict


def service_at(path: Path) -> GameService:
    return GameService(SQLiteStore(path))


def human_choice(service: GameService, record: GameRecord) -> GameRecord:
    decision = record.state.pending
    assert decision is not None and decision.player in record.human_seats
    choice = choose(
        service.view(record.game_id, decision.player),
        decision,
        BotState("economy", record.revision),
    )
    return service.submit(record.game_id, choice.command, player=decision.player)


@pytest.mark.parametrize("players", [2, 3, 4])
def test_all_human_games_finish_through_the_service(tmp_path: Path, players: int) -> None:
    service = service_at(tmp_path / "games.sqlite3")
    record = service.create(
        GameConfig(player_count=players), 23, (), human_seats=frozenset(range(players))
    )
    assert record.bots == record.bot_seats == ()
    seen: set[int] = set()
    for _ in range(2000):
        if record.state.phase == "finished":
            break
        assert service.advance_bots(record.game_id, record.revision) == record
        decision = record.state.pending
        assert decision is not None
        seen.add(decision.player)
        for player in range(players):
            view = service.view(record.game_id, player)
            assert view.hand == tuple(record.state.players[player].hand)
            assert (view.pending is not None) == (player == decision.player)
        record = human_choice(service, record)
    assert record.state.phase == "finished"
    assert len(record.state.scores) == players
    assert seen == set(range(players))
    assert len(service.store.history(record.game_id)) == record.revision


@pytest.mark.parametrize("humans", [frozenset({0, 2}), frozenset({1, 3})])
def test_noncontiguous_bots_keep_their_own_profiles_and_state(
    tmp_path: Path, humans: frozenset[int]
) -> None:
    service = service_at(tmp_path / "games.sqlite3")
    record = service.create(
        GameConfig(player_count=4), 17, ("attack", "engine"), human_seats=humans
    )
    bot_seats = tuple(player for player in range(4) if player not in humans)
    assert record.bot_seats == bot_seats
    assert tuple(bot.profile for bot in record.bots) == ("attack", "engine")
    observed: set[int] = set()
    for _ in range(100):
        decision = record.state.pending
        assert decision is not None
        if decision.player in humans:
            assert service.advance_bots(record.game_id, record.revision) == record
            record = human_choice(service, record)
        else:
            observed.add(decision.player)
            before = record
            record = service.advance_bots(record.game_id, record.revision, max_steps=1)
            assert record.revision == before.revision + 1
            for seat, old, new in zip(bot_seats, before.bots, record.bots, strict=True):
                assert new.profile == old.profile
                assert new.seed == old.seed
                assert new.decisions == old.decisions + (seat == decision.player)
    assert observed == set(bot_seats)
    saved = cast(dict[str, object], json.loads(service.store.load(record.game_id).snapshot))
    by_seat = cast(dict[str, object], saved["bots"])
    assert set(by_seat) == {str(seat) for seat in bot_seats}
    assert saved["human_seats"] == sorted(humans)


@pytest.mark.parametrize(
    "humans",
    [
        frozenset[int](),
        frozenset({-1}),
        frozenset({3}),
        frozenset({True}),
        frozenset({0.5}),
        frozenset({"0"}),
    ],
)
def test_invalid_human_assignments_create_no_save(tmp_path: Path, humans: object) -> None:
    service = service_at(tmp_path / "games.sqlite3")
    with pytest.raises(ValueError, match="[Hh]uman seat"):
        service.create(GameConfig(player_count=3), 3, (), human_seats=cast(frozenset[int], humans))
    assert service.list_games() == []


def test_profiles_are_required_only_for_bot_seats(tmp_path: Path) -> None:
    service = service_at(tmp_path / "games.sqlite3")
    with pytest.raises(ValueError, match="each opponent"):
        service.create(GameConfig(player_count=3), 3, ("economy",), human_seats=frozenset({1}))
    with pytest.raises(ValueError, match="each opponent"):
        service.create(GameConfig(), 3, ("economy",), human_seats=frozenset({0, 1}))
    with pytest.raises(ValueError, match="strategy"):
        service.create(GameConfig(), 3, ("unknown",), human_seats=frozenset({1}))
    assert service.list_games() == []


@pytest.mark.parametrize("actor", [-1, 0, 2, 3, True, False, "1", 1.0])
def test_only_configured_human_indices_can_view_or_submit(tmp_path: Path, actor: object) -> None:
    service = service_at(tmp_path / "games.sqlite3")
    record = service.create(
        GameConfig(player_count=3), 4, ("attack", "engine"), human_seats=frozenset({1})
    )
    decision = record.state.pending
    assert decision is not None
    before = service.store.load(record.game_id)
    with pytest.raises(ValueError, match="human seat"):
        service.view(record.game_id, cast(int, actor))
    with pytest.raises(ValueError, match="human seat"):
        service.submit(
            record.game_id, Command(decision.id, record.revision, ()), player=cast(int, actor)
        )
    assert service.store.load(record.game_id) == before
    assert service.store.history(record.game_id) == []


@pytest.mark.parametrize("attacker", [0, 2])
def test_reaction_belongs_to_its_human_owner_not_the_active_player(
    tmp_path: Path, attacker: int
) -> None:
    path = tmp_path / "games.sqlite3"
    service = service_at(path)
    target = attacker + 1
    humans = frozenset({1, 3}) if attacker == 0 else frozenset({1, 2, 3})
    state = new_game(GameConfig(player_count=4), 21)
    state.active_player = attacker
    state.phase = "action"
    attack = Card(f"c{state.next_instance_id}", "k14")
    protection = Card(f"c{state.next_instance_id + 1}", "k16")
    state.next_instance_id += 2
    state.supply["k14"] -= 1
    state.supply["k16"] -= 1
    state.players[attacker].hand.append(attack)
    state.players[target].hand.append(protection)
    assert state.pending is not None
    state.pending = Decision(
        state.pending.id,
        attacker,
        "menu",
        "action",
        (Option(attack.id, attack.definition, attack.id), Option("end-actions")),
        1,
        1,
    )
    state.pending_effect = Effect("action", attacker)
    service.store.create(
        "reaction",
        json.dumps(
            {
                "schema": 2,
                "engine": state_to_json(state),
                "human_seats": sorted(humans),
                "bots": {
                    str(seat): asdict(BotState("attack", seat))
                    for seat in range(4)
                    if seat not in humans
                },
            }
        ),
        "{}",
        "common-ground",
    )
    if attacker in humans:
        record = service.submit(
            "reaction", Command(state.pending.id, 0, (attack.id,)), player=attacker
        )
    else:
        record = service.advance_bots("reaction", 0)
    decision = record.state.pending
    assert decision is not None and decision.prompt == "reaction" and decision.player == target
    assert record.state.active_player == attacker
    service = service_at(path)
    assert service.load("reaction") == record
    assert service.view("reaction", target).pending == decision
    wrong_actor = next(player for player in humans if player != target)
    assert service.view("reaction", wrong_actor).pending is None
    with pytest.raises(InvalidCommand, match="your decision"):
        service.submit(
            "reaction", Command(decision.id, record.revision, ("yes",)), player=wrong_actor
        )
    assert service.advance_bots("reaction", record.revision) == record
    accepted = service.submit(
        "reaction", Command(decision.id, record.revision, ("yes",)), player=target
    )
    assert accepted.state.players[target].hand == record.state.players[target].hand
    assert accepted.revision == record.revision + 1
    with pytest.raises(StorageConflict):
        service.submit("reaction", Command(decision.id, record.revision, ("yes",)), player=target)
    assert service.load("reaction") == accepted
    assert len(service.store.history("reaction")) == accepted.revision


def test_mixed_controller_save_resume_has_identical_future(tmp_path: Path) -> None:
    control_service = service_at(tmp_path / "control.sqlite3")
    resumed_path = tmp_path / "resumed.sqlite3"
    resumed_service = service_at(resumed_path)
    config = GameConfig(player_count=4)
    humans = frozenset({1, 3})
    control = control_service.create(config, 31, ("engine", "attack"), human_seats=humans)
    resumed = resumed_service.create(config, 31, ("engine", "attack"), human_seats=humans)
    for _ in range(150):
        resumed_service = service_at(resumed_path)
        resumed = resumed_service.load(resumed.game_id)
        decision = control.state.pending
        assert decision is not None
        if decision.player in humans:
            control = human_choice(control_service, control)
            resumed = human_choice(resumed_service, resumed)
        else:
            control = control_service.advance_bots(control.game_id, control.revision, 1)
            resumed = resumed_service.advance_bots(resumed.game_id, resumed.revision, 1)
        assert state_to_json(resumed.state) == state_to_json(control.state)
        assert resumed.bots == control.bots
        assert resumed.human_seats == control.human_seats == humans
    assert all(bot.decisions > 0 for bot in resumed.bots)


def test_original_local_save_loads_without_rewrite_then_upgrades_on_transition(
    tmp_path: Path,
) -> None:
    service = service_at(tmp_path / "games.sqlite3")
    state = new_game(GameConfig(player_count=3), 42)
    bots = (
        BotState("engine", 42 ^ 0x9E3779B97F4A7C15),
        BotState("attack", 42 ^ (2 * 0x9E3779B97F4A7C15)),
    )
    # This is the exact schema emitted by the original local application.
    original = service.store.create(
        "legacy",
        json.dumps(
            {"schema": 1, "engine": state_to_json(state), "bots": [asdict(bot) for bot in bots]}
        ),
        json.dumps(
            {
                "players": [player.name for player in state.players],
                "strategies": ["engine", "attack"],
            }
        ),
        "orbital",
    )
    record = service.load("legacy")
    assert record.human_seats == frozenset({0}) and record.bot_seats == (1, 2)
    assert record.state == state and record.bots == bots
    assert service.store.load("legacy") == original
    control = service.create(GameConfig(player_count=3), 42, ("engine", "attack"), "orbital")
    assert control.bots == bots
    assert state.pending is not None
    if state.pending.player == 0:
        record = human_choice(service, record)
        control = human_choice(service, control)
    else:
        record = service.advance_bots("legacy", 0, 1)
        control = service.advance_bots(control.game_id, 0, 1)
    assert record.state == control.state and record.bots == control.bots
    saved = service.store.load("legacy")
    assert saved.metadata == original.metadata and saved.theme_id == "orbital"
    payload = cast(dict[str, object], json.loads(saved.snapshot))
    assert payload["schema"] == 2
    assert payload["human_seats"] == [0]
    assert service_at(tmp_path / "games.sqlite3").load("legacy") == record


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", True),
        ("human_seats", None),
        ("human_seats", []),
        ("human_seats", [0, 0]),
        ("human_seats", [True]),
        ("human_seats", [1.0]),
        ("human_seats", ["1"]),
        ("human_seats", [3]),
        ("human_seats", [-1]),
        ("bots", []),
        ("bots", {}),
        ("bots", {"0": {}}),
        ("bots", {"01": {}}),
    ],
)
def test_corrupt_controller_save_is_rejected_without_rewriting(
    tmp_path: Path, field: str, value: object
) -> None:
    service = service_at(tmp_path / "games.sqlite3")
    valid = service.create(GameConfig(), 4, ("economy",), human_seats=frozenset({1}))
    payload = cast(dict[str, object], json.loads(service.store.load(valid.game_id).snapshot))
    payload[field] = value
    original = service.store.create("corrupt", json.dumps(payload), "{}", "common-ground")
    with pytest.raises(SaveFormatError):
        service.load("corrupt")
    assert service.store.load("corrupt") == original
