"""Save compatibility, malformed data, and interrupted private decisions."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from sway.engine import (
    Command,
    GameConfig,
    InvalidSnapshot,
    advance,
    new_game,
    state_from_json,
    state_to_json,
)
from sway.engine.models import Effect, Option


@pytest.mark.parametrize(
    "snapshot",
    [
        "not JSON",
        "[]",
        "null",
        "{}",
        '{"version":2,"state":{}}',
        '{"version":true,"state":{}}',
        '{"version":1,"state":[]}',
        '{"version":1,"state":{}}',
    ],
)
def test_unsupported_or_malformed_snapshot_is_rejected(snapshot: str) -> None:
    with pytest.raises(InvalidSnapshot):
        state_from_json(snapshot)


@pytest.mark.parametrize(
    "old,new",
    [
        ('"hand":[', '"hand":null,"unused":['),
        ('"name":"Player 1"', '"name":17'),
        ('"silver_played":false', '"silver_played":1'),
        ('"definition":"treasure1"', '"definition":"unknown"'),
        ('"kind":"menu"', '"kind":"alien"'),
        ('"phase":"buy"', '"phase":"sleep"'),
        ('"player_count":2', '"player_count":3'),
        ('"curse":10', '"curse":-1'),
        ('"coins":0', '"coins":-1'),
        ('"minimum":1', '"minimum":-1'),
    ],
)
def test_corrupted_typed_fields_fail_clearly(old: str, new: str) -> None:
    snapshot = state_to_json(new_game(GameConfig(), 8))
    assert old in snapshot
    with pytest.raises(InvalidSnapshot):
        state_from_json(snapshot.replace(old, new))


def test_duplicate_cards_and_inconsistent_decisions_rejected() -> None:
    state = new_game(GameConfig(), 0)
    state.players[0].hand.append(state.players[0].deck[0])
    with pytest.raises(InvalidSnapshot, match="more than one zone"):
        state_from_json(state_to_json(state))
    state.players[0].hand.pop()
    assert state.pending is not None
    state.pending = replace(state.pending, options=(Option("same"), Option("same")))
    with pytest.raises(InvalidSnapshot, match="Duplicate"):
        state_from_json(state_to_json(state))
    state.pending = None
    with pytest.raises(InvalidSnapshot, match="continuation"):
        state_from_json(state_to_json(state))


def test_finished_snapshot_cannot_contain_pending_work() -> None:
    state = new_game(GameConfig(), 0)
    state.phase = "finished"
    with pytest.raises(InvalidSnapshot, match="unresolved"):
        state_from_json(state_to_json(state))
    state.pending = None
    state.pending_effect = None
    state.effects = [Effect("resolve", 0, card_id="k24")]
    with pytest.raises(InvalidSnapshot, match="unresolved"):
        state_from_json(state_to_json(state))
    state.effects = []
    assert state_from_json(state_to_json(state)) == state


def test_save_is_plain_json_and_preserves_names_without_html_processing() -> None:
    state = new_game(GameConfig(player_names=("<script>name</script>", "Δοκιμή")), -12)
    snapshot = state_to_json(state)
    assert json.loads(snapshot)["version"] == 1
    assert state_from_json(snapshot) == state
    assert state.pending is not None
    command = Command(state.pending.id, state.revision, ("end-turn",))
    uninterrupted = advance(state, command)
    resumed = advance(state_from_json(snapshot), command)
    assert uninterrupted == resumed
