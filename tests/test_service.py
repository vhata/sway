"""Save/resume orchestration must preserve the same future game, not just a UI."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from sway.bots import BotState, choose
from sway.engine import Command, GameConfig, InvalidCommand, state_to_json, view_for
from sway.service import GameRecord, GameService
from sway.storage import SaveFormatError, SQLiteStore, StorageConflict


def make_service(path: Path) -> GameService:
    return GameService(SQLiteStore(path))


def step(service: GameService, record: GameRecord) -> GameRecord:
    decision = record.state.pending
    if decision is None:
        return record
    if decision.player == 0:
        choice = choose(view_for(record.state, 0), decision, BotState("engine", record.revision))
        return service.submit(record.game_id, choice.command)
    return service.advance_bots(record.game_id, record.revision, max_steps=1)


def test_save_resume_preserves_engine_and_bot_future(tmp_path: Path) -> None:
    control_service = make_service(tmp_path / "control.sqlite3")
    resumed_path = tmp_path / "resumed.sqlite3"
    resumed_service = make_service(resumed_path)
    config = GameConfig(player_count=3)
    control = control_service.create(config, 42, ("engine", "attack"))
    resumed = resumed_service.create(config, 42, ("engine", "attack"))
    for _ in range(75):
        control = step(control_service, control)
        resumed_service = make_service(resumed_path)
        resumed = step(resumed_service, resumed_service.load(resumed.game_id))
        assert state_to_json(resumed.state) == state_to_json(control.state)
        assert resumed.bots == control.bots
    assert len(resumed_service.store.history(resumed.game_id)) == resumed.revision


def test_theme_does_not_change_decision_or_randomness(tmp_path: Path) -> None:
    service = make_service(tmp_path / "games.sqlite3")
    record = service.create(GameConfig(), 7, ("economy",))
    assert record.theme_id == "common-ground"
    themed = service.set_theme(record.game_id, "orbital")
    assert themed.theme_id == "orbital"
    assert themed.revision == record.revision
    assert state_to_json(themed.state) == state_to_json(record.state)
    assert themed.bots == record.bots
    with pytest.raises(ValueError, match="theme"):
        service.set_theme(record.game_id, "../escape")
    assert service.list_games()[0].theme_id == "orbital"


def test_stale_or_wrong_seat_submission_preserves_save(tmp_path: Path) -> None:
    service = make_service(tmp_path / "games.sqlite3")
    record = service.create(GameConfig(), 3, ("attack",))
    decision = record.state.pending
    assert decision is not None
    with pytest.raises(StorageConflict):
        service.submit(record.game_id, Command(decision.id, -1, ()))
    with pytest.raises(StorageConflict):
        service.advance_bots(record.game_id, -1)
    with pytest.raises(ValueError):
        service.view(record.game_id, 1)
    with pytest.raises(ValueError):
        service.advance_bots(record.game_id, record.revision, max_steps=100)
    if decision.player != 0:
        with pytest.raises(InvalidCommand, match="your decision"):
            service.submit(record.game_id, Command(decision.id, record.revision, ()))
    assert service.load(record.game_id) == record


def test_bots_stop_at_human_decision(tmp_path: Path) -> None:
    service = make_service(tmp_path / "games.sqlite3")
    record = service.create(GameConfig(player_count=4), 99, ("economy", "engine", "attack"))
    for _ in range(20):
        record = service.advance_bots(record.game_id, record.revision, max_steps=32)
        if record.state.pending is not None and record.state.pending.player == 0:
            break
    assert record.state.pending is not None
    assert record.state.pending.player == 0
    assert service.advance_bots(record.game_id, record.revision) == record


def test_bad_profiles_and_versions_do_not_destroy_original(tmp_path: Path) -> None:
    service = make_service(tmp_path / "games.sqlite3")
    with pytest.raises(ValueError, match="each opponent"):
        service.create(GameConfig(), 1, ())
    with pytest.raises(ValueError, match="strategy"):
        service.create(GameConfig(), 1, ("omniscient",))
    record = service.create(GameConfig(), 1, ("economy",))
    future = json.dumps({"schema": 999, "engine": state_to_json(record.state), "bots": []})
    original = service.store.create("future", future, "{}", "common-ground")
    with pytest.raises(SaveFormatError, match="version"):
        service.load("future")
    assert service.store.load("future") == original
    assert service.load(record.game_id) == record
    assert {game.game_id for game in service.list_games()} == {"future", record.game_id}
    assert service.create(GameConfig(), 2, ("engine",)).game_id != record.game_id


def test_storage_history_is_replayable(tmp_path: Path) -> None:
    from sway.engine import advance, new_game

    service = make_service(tmp_path / "games.sqlite3")
    config = GameConfig()
    record = service.create(config, 9, ("engine",))
    initial = new_game(config, 9)
    commands: list[Command] = []
    for _ in range(15):
        decision = record.state.pending
        assert decision is not None
        bot = BotState("engine", record.revision)
        if decision.player == 0:
            cmd = choose(view_for(record.state, 0), decision, bot).command
        else:
            cmd = choose(view_for(record.state, 1), decision, record.bots[0]).command
        commands.append(cmd)
        record = step(service, record)
    replayed = initial
    for command in commands:
        replayed = advance(replayed, command).state
    assert state_to_json(replayed) == state_to_json(record.state)
    history = service.store.history(record.game_id)
    assert [item.command for item in history] == [
        json.dumps(asdict(command), sort_keys=True) for command in commands
    ]
